"""Held-out A/B for temporal credit assignment from terminal duel outcomes.

The canonical learner gives every learned decision in a duel the same terminal
win/loss reward (apart from the shared 1/sqrt(N) episode scale).  This treatment
keeps that normalization but exponentially discounts terminal credit by distance
from the end of the duel.

Half-life is 256 learned decisions:
- final decision: weight 1.0
- 256 decisions before terminal: weight 0.5
- 512 decisions before terminal: weight 0.25

This is a generic RL credit-assignment change.  It adds no card values, matchup
labels, archetype knowledge, historical/meta data, or human strategy heuristics.
"""
from __future__ import annotations

import argparse
import json
import math

from .credit_ab_eval import (
    _block_slice, _evaluate_arm, _paired_summary, _summarize_rows, _train_arm,
)
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .pilot_eval import _usable_candidates


class DiscountedTerminalPolicy(SparsePolicy):
    """Canonical terminal REINFORCE with distance-to-terminal credit discount."""

    half_life_decisions = 256.0

    @classmethod
    def terminal_weight(cls, distance_from_terminal):
        return 2.0 ** (-float(distance_from_terminal) / cls.half_life_decisions)

    def update_episode(self, steps, winner, scale=None):
        if winner not in (0, 1):
            return
        if not steps:
            return
        if scale is None:
            scale = 1.0 / math.sqrt(len(steps))

        n = len(steps)
        for index, step in enumerate(steps):
            distance = n - 1 - index
            temporal = self.terminal_weight(distance)
            reward = (1.0 if step.player == winner else -1.0) * temporal
            probs = self.probabilities(step.option_features)
            lr = self.learning_rate * scale
            for option_index, features in enumerate(step.option_features):
                coefficient = reward * (
                    (1.0 if option_index == step.chosen else 0.0)
                    - probs[option_index]
                )
                delta = lr * coefficient
                if not delta:
                    continue
                for feature in features:
                    self.weights[feature] = self.weights.get(feature, 0.0) + delta
        self.weights = {
            key: value for key, value in self.weights.items()
            if abs(value) >= 1e-12
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--blocks', type=int, default=6)
    p.add_argument('--block-offset', type=int, default=0)
    p.add_argument('--train-games', type=int, default=64)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=4)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=331000)
    p.add_argument('--eval-seed', type=int, default=341000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(a.blocks, a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck) < 1:
        raise ValueError('discounted-terminal A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('discounted-terminal A/B requires at least two training decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = (a.block_offset + a.blocks) * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError(
            f'discounted-terminal A/B needs candidates through block '
            f'{a.block_offset + a.blocks - 1}, found only {len(usable)} usable candidates'
        )

    blocks = []
    all_control_eval = []
    all_treatment_eval = []
    all_training_complete = True
    all_eval_complete = True
    all_frozen = True

    for block in range(a.blocks):
        cohort_block = a.block_offset + block
        train_pool, eval_pool = _block_slice(
            usable, cohort_block, a.train_decks, a.eval_decks
        )
        control, control_train, control_ok, train_seed, policy_seed = _train_arm(
            a, mapped, train_pool, block, SparsePolicy
        )
        treatment, treatment_train, treatment_ok, t_seed, t_policy_seed = _train_arm(
            a, mapped, train_pool, block, DiscountedTerminalPolicy
        )
        if train_seed != t_seed or policy_seed != t_policy_seed:
            raise RuntimeError('discounted-terminal A/B training seeds diverged')

        control_eval = []
        treatment_eval = []
        control_frozen = treatment_frozen = False
        eval_seed = a.eval_seed + block * 1000
        if control_ok and treatment_ok:
            control_eval, control_frozen, c_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, control, block
            )
            treatment_eval, treatment_frozen, t_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, treatment, block
            )
            if c_eval_seed != t_eval_seed:
                raise RuntimeError('discounted-terminal A/B evaluation seeds diverged')
            eval_seed = c_eval_seed

        planned = a.eval_decks * a.pairs_per_deck * 2
        control_eval_ok = len(control_eval) == planned and all(r.get('completed') for r in control_eval)
        treatment_eval_ok = len(treatment_eval) == planned and all(r.get('completed') for r in treatment_eval)
        paired, pair_rows = _paired_summary(control_eval, treatment_eval)

        blocks.append({
            'block': block,
            'candidate_cohort_block': cohort_block,
            'train_candidate_ids': [cid for cid, _ in train_pool],
            'eval_candidate_ids': [cid for cid, _ in eval_pool],
            'train_seed_start': train_seed,
            'eval_seed_start': eval_seed,
            'policy_seed': policy_seed,
            'control': {
                'policy': 'canonical_terminal_credit',
                'weight_count': len(control.weights),
                'training_complete': control_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
            },
            'treatment': {
                'policy': 'terminal_credit_half_life_256_decisions',
                'weight_count': len(treatment.weights),
                'training_complete': treatment_ok,
                'policy_frozen_during_evaluation': treatment_frozen,
                'training': _summarize_rows(treatment_train),
                'evaluation': _summarize_rows(treatment_eval),
            },
            'paired_outcomes': paired,
            'paired_results': pair_rows,
        })

        all_control_eval.extend(control_eval)
        all_treatment_eval.extend(treatment_eval)
        all_training_complete &= control_ok and treatment_ok
        all_eval_complete &= control_eval_ok and treatment_eval_ok
        all_frozen &= control_frozen and treatment_frozen

        if not (
            control_ok and treatment_ok and control_eval_ok and treatment_eval_ok
            and control_frozen and treatment_frozen
        ):
            break

    control_summary = _summarize_rows(all_control_eval)
    treatment_summary = _summarize_rows(all_treatment_eval)
    paired, paired_rows = _paired_summary(all_control_eval, all_treatment_eval)
    planned_total = a.blocks * a.eval_decks * a.pairs_per_deck * 2

    report = {
        'purpose': 'discounted_terminal_credit_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'training_games_per_block_per_arm': a.train_games,
        'control_policy': 'canonical equal terminal reward per decision',
        'treatment_policy': 'terminal reward half-life 256 learned decisions',
        'configuration': {
            'blocks': a.blocks,
            'block_offset': a.block_offset,
            'train_decks_per_block': a.train_decks,
            'eval_decks_per_block': a.eval_decks,
            'pairs_per_eval_deck': a.pairs_per_deck,
            'planned_eval_games_per_arm': planned_total,
            'train_seed_base': a.train_seed,
            'eval_seed_base': a.eval_seed,
            'policy_seed_base': a.policy_seed,
            'terminal_half_life_decisions': DiscountedTerminalPolicy.half_life_decisions,
        },
        'control': control_summary,
        'treatment': treatment_summary,
        'treatment_minus_control_win_rate': (
            treatment_summary['learned_win_rate'] - control_summary['learned_win_rate']
            if treatment_summary['learned_win_rate'] is not None
            and control_summary['learned_win_rate'] is not None else None
        ),
        'treatment_minus_control_score_rate': (
            treatment_summary['learned_score_rate'] - control_summary['learned_score_rate']
            if treatment_summary['learned_score_rate'] is not None
            and control_summary['learned_score_rate'] is not None else None
        ),
        'paired_outcomes': paired,
        'paired_results': paired_rows,
        'all_training_complete': all_training_complete,
        'all_evaluation_complete': all_eval_complete,
        'all_policies_frozen': all_frozen,
        'blocks': blocks,
        'note': (
            'Pilot-skill evidence only. Temporal discount is generic outcome '
            'credit assignment and introduces no external strategy information.'
        ),
    }
    dump(ROOT/'reports/discounted_terminal_ab.json', report)
    print(json.dumps({
        'blocks_completed': len(blocks),
        'eval_per_arm': control_summary['completed'],
        'eval_planned_per_arm': planned_total,
        'control_score_rate': control_summary['learned_score_rate'],
        'treatment_score_rate': treatment_summary['learned_score_rate'],
        'treatment_minus_control_score_rate': report['treatment_minus_control_score_rate'],
        'paired': paired,
        'control_fallback': control_summary['fallback_decisions'],
        'treatment_fallback': treatment_summary['fallback_decisions'],
    }))

    if not all_training_complete:
        raise SystemExit('discounted-terminal A/B training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('discounted-terminal A/B mutated a frozen evaluation policy')
    if not all_eval_complete:
        raise SystemExit('discounted-terminal A/B evaluation did not complete cleanly')
    if control_summary['completed'] != planned_total or treatment_summary['completed'] != planned_total:
        raise SystemExit('discounted-terminal A/B did not complete all planned held-out games')


if __name__ == '__main__':
    main()

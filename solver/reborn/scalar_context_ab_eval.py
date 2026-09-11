"""Held-out A/B for compact scalar-state conditioning with adequate self-play volume.

The canonical SparsePolicy includes phase/turn-side/LP/hand/field/grave state
tokens, but those tokens are identical across legal options at a decision and
therefore cancel from a linear softmax. This treatment makes those already-safe
state facts decision-relevant by crossing them with a small set of option
anchors.

Unlike the earlier broad contextual experiment, this treatment does NOT include
known-card context, zone card identities from the observation, deck/archetype
labels, matchup labels, or human heuristics. Both arms receive the same larger
self-play training volume so the experiment isolates representation rather than
training quantity.
"""
from __future__ import annotations

import argparse
import json

from .credit_ab_eval import (
    _block_slice, _evaluate_arm, _paired_summary, _summarize_rows, _train_arm,
)
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .pilot_eval import _usable_candidates


class ScalarContextPolicy(SparsePolicy):
    """Canonical policy plus coarse public-state x option interactions."""

    @staticmethod
    def _unique(values):
        return tuple(dict.fromkeys(values))

    def _contexts(self, observation):
        return tuple(
            feature for feature in self._state_features(observation)
            if feature != 'bias'
        )

    def _cross(self, observation, anchors):
        anchors = self._unique(anchors)
        return tuple(
            f'scalar_ctx:{context}|{anchor}'
            for context in self._contexts(observation)
            for anchor in anchors
        )

    def action_features(self, prompt, observation, action):
        features = list(super().action_features(prompt, observation, action))
        kind = prompt['kind']
        label = action.get('label', 'unknown')
        anchors = [f'kind_label:{kind}|{label}']
        card = action.get('card')
        if card and 'code' in card:
            anchors.append(f'card_label:{card["code"]}|{label}')
        if action.get('description') is not None:
            anchors.append(f'desc_label:{action["description"]}|{label}')
        if action.get('position') is not None:
            anchors.append(f'position:{action["position"]}|{label}')
        features.extend(self._cross(observation, anchors))
        return tuple(features)

    def card_features(self, prompt, observation, card):
        features = list(super().card_features(prompt, observation, card))
        anchors = [f'kind_label:{prompt["kind"]}|select_card']
        if 'code' in card:
            anchors.append(f'card_label:{card["code"]}|select_card')
        else:
            rel = 'self' if card.get('controller') == observation['viewer'] else 'opp'
            anchors.append(f'candidate_slot:{rel}|{card.get("location")}|{card.get("sequence")}')
        features.extend(self._cross(observation, anchors))
        return tuple(features)

    def complex_features(self, prompt, observation, option):
        features = list(super().complex_features(prompt, observation, option))
        kind = prompt['kind']
        label = option.get('label', 'complex')
        anchors = [f'kind_label:{kind}|{label}']
        for card in option.get('selected_cards', ()):
            if 'code' in card:
                anchors.append(f'card_label:{card["code"]}|{label}')
        if option.get('selected_count') is not None:
            anchors.append(f'selected_count:{option["selected_count"]}')
        features.extend(self._cross(observation, anchors))
        return tuple(features)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--blocks', type=int, default=6)
    p.add_argument('--train-games', type=int, default=64)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=4)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=171000)
    p.add_argument('--eval-seed', type=int, default=181000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(a.blocks, a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck) < 1:
        raise ValueError('scalar-context A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('scalar-context A/B requires at least two training decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = a.blocks * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError(
            f'scalar-context A/B needs {needed} usable candidates, found {len(usable)}'
        )

    blocks = []
    all_control_eval = []
    all_treatment_eval = []
    all_training_complete = True
    all_eval_complete = True
    all_frozen = True

    for block in range(a.blocks):
        train_pool, eval_pool = _block_slice(usable, block, a.train_decks, a.eval_decks)

        control, control_train, control_ok, train_seed, policy_seed = _train_arm(
            a, mapped, train_pool, block, SparsePolicy
        )
        treatment, treatment_train, treatment_ok, t_seed, t_policy_seed = _train_arm(
            a, mapped, train_pool, block, ScalarContextPolicy
        )
        if train_seed != t_seed or policy_seed != t_policy_seed:
            raise RuntimeError('scalar-context A/B training seeds diverged between arms')

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
                raise RuntimeError('scalar-context A/B evaluation seeds diverged')
            eval_seed = c_eval_seed

        planned = a.eval_decks * a.pairs_per_deck * 2
        control_eval_ok = len(control_eval) == planned and all(r.get('completed') for r in control_eval)
        treatment_eval_ok = len(treatment_eval) == planned and all(r.get('completed') for r in treatment_eval)
        paired, pair_rows = _paired_summary(control_eval, treatment_eval)

        blocks.append({
            'block': block,
            'train_candidate_ids': [cid for cid, _ in train_pool],
            'eval_candidate_ids': [cid for cid, _ in eval_pool],
            'train_seed_start': train_seed,
            'eval_seed_start': eval_seed,
            'policy_seed': policy_seed,
            'control': {
                'policy': 'canonical_sparse_v2',
                'weight_count': len(control.weights),
                'training_complete': control_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
            },
            'treatment': {
                'policy': 'canonical_plus_scalar_state_option_interactions',
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
        'purpose': 'scalar_state_conditioning_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'training_games_per_block_per_arm': a.train_games,
        'control_policy': 'canonical sparse policy',
        'treatment_policy': 'canonical + coarse scalar-state x option interactions',
        'configuration': {
            'blocks': a.blocks,
            'train_decks_per_block': a.train_decks,
            'eval_decks_per_block': a.eval_decks,
            'pairs_per_eval_deck': a.pairs_per_deck,
            'planned_eval_games_per_arm': planned_total,
            'train_seed_base': a.train_seed,
            'eval_seed_base': a.eval_seed,
            'policy_seed_base': a.policy_seed,
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
            'Pilot-skill evidence only. Treatment uses only public scalar state '
            'already present in the canonical observation and adds no card-value '
            'or strategy prior. Mirror candidate outcomes are not deck rankings.'
        ),
    }
    dump(ROOT/'reports/scalar_context_ab.json', report)
    print(json.dumps({
        'blocks_completed': len(blocks),
        'eval_per_arm': control_summary['completed'],
        'eval_planned_per_arm': planned_total,
        'control_wins': control_summary['learned_wins'],
        'control_losses': control_summary['learned_losses'],
        'control_draws': control_summary['learned_draws'],
        'control_score_rate': control_summary['learned_score_rate'],
        'treatment_wins': treatment_summary['learned_wins'],
        'treatment_losses': treatment_summary['learned_losses'],
        'treatment_draws': treatment_summary['learned_draws'],
        'treatment_score_rate': treatment_summary['learned_score_rate'],
        'treatment_minus_control_score_rate': report['treatment_minus_control_score_rate'],
        'paired': paired,
        'control_fallback': control_summary['fallback_decisions'],
        'treatment_fallback': treatment_summary['fallback_decisions'],
    }))

    if not all_training_complete:
        raise SystemExit('scalar-context A/B training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('scalar-context A/B mutated a frozen evaluation policy')
    if not all_eval_complete:
        raise SystemExit('scalar-context A/B evaluation did not complete cleanly')
    if control_summary['completed'] != planned_total or treatment_summary['completed'] != planned_total:
        raise SystemExit('scalar-context A/B did not complete all planned held-out games')


if __name__ == '__main__':
    main()

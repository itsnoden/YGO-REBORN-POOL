"""Held-out A/B for a minimal zero-prior chain-context policy.

The canonical sparse learner contains state terms that are common to every legal
option at a decision and therefore cancel from a linear softmax. A previous
experiment crossed a large visible state (including known card identities) with
many action features and overfit. This treatment is intentionally much smaller:
ONLY explicit ``chain`` actions receive three safe context interactions:

- current phase x action anchor
- whose turn it is relative to the acting player x action anchor
- current public chain depth x action anchor

No card values, archetypes, matchup labels, historical strategy, community data,
or human heuristics are added. The canonical learner is not modified.
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


class ChainContextPolicy(SparsePolicy):
    """Experimental policy with tiny context interactions on chain actions only."""

    def action_features(self, prompt, observation, action):
        features = list(super().action_features(prompt, observation, action))
        if prompt.get('kind') != 'chain':
            return tuple(features)

        label = action.get('label', 'unknown')
        anchors = [f'kind_label:chain|{label}']
        card = action.get('card')
        if card and 'code' in card:
            anchors.append(f'card_label:{card["code"]}|{label}')
        if action.get('description') is not None:
            anchors.append(f'desc_label:{action["description"]}|{label}')

        viewer = observation['viewer']
        turn_player = observation.get('turn_player')
        if turn_player == viewer:
            turn_side = 'self'
        elif turn_player in (0, 1):
            turn_side = 'opp'
        else:
            turn_side = 'unknown'
        phase = observation.get('phase')
        chain_depth = min(8, max(0, len(observation.get('chains', ()))))
        contexts = (
            f'phase:{phase}',
            f'turn_side:{turn_side}',
            f'chain_depth:{chain_depth}',
        )
        for context in contexts:
            for anchor in dict.fromkeys(anchors):
                features.append(f'chain_ctx:{context}|{anchor}')
        return tuple(features)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--blocks', type=int, default=6)
    p.add_argument('--train-games', type=int, default=16)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=4)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=111000)
    p.add_argument('--eval-seed', type=int, default=121000)
    p.add_argument('--policy-seed', type=int, default=20260907)
    a = p.parse_args()

    if min(a.blocks, a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck) < 1:
        raise ValueError('chain-context A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('chain-context A/B requires at least two training decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = a.blocks * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError(f'chain-context A/B needs {needed} usable candidates, found {len(usable)}')

    blocks = []
    all_control_eval = []
    all_treatment_eval = []
    all_training_complete = True
    all_eval_complete = True
    all_frozen = True

    for block in range(a.blocks):
        train_pool, eval_pool = _block_slice(usable, block, a.train_decks, a.eval_decks)
        control, control_train, control_train_ok, train_seed, policy_seed = _train_arm(
            a, mapped, train_pool, block, SparsePolicy
        )
        treatment, treatment_train, treatment_train_ok, treatment_train_seed, treatment_policy_seed = _train_arm(
            a, mapped, train_pool, block, ChainContextPolicy
        )
        if train_seed != treatment_train_seed or policy_seed != treatment_policy_seed:
            raise RuntimeError('chain-context A/B training seeds diverged between arms')

        control_eval = []
        treatment_eval = []
        control_frozen = treatment_frozen = False
        eval_seed = a.eval_seed + block * 1000
        if control_train_ok and treatment_train_ok:
            control_eval, control_frozen, control_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, control, block
            )
            treatment_eval, treatment_frozen, treatment_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, treatment, block
            )
            if control_eval_seed != treatment_eval_seed:
                raise RuntimeError('chain-context A/B evaluation seeds diverged between arms')
            eval_seed = control_eval_seed

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
                'training_complete': control_train_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
            },
            'treatment': {
                'policy': 'chain_context_phase_turn_depth_only',
                'weight_count': len(treatment.weights),
                'training_complete': treatment_train_ok,
                'policy_frozen_during_evaluation': treatment_frozen,
                'training': _summarize_rows(treatment_train),
                'evaluation': _summarize_rows(treatment_eval),
            },
            'paired_outcomes': paired,
            'paired_results': pair_rows,
        })
        all_control_eval.extend(control_eval)
        all_treatment_eval.extend(treatment_eval)
        all_training_complete &= control_train_ok and treatment_train_ok
        all_eval_complete &= control_eval_ok and treatment_eval_ok
        all_frozen &= control_frozen and treatment_frozen
        if not (control_train_ok and treatment_train_ok and control_eval_ok and treatment_eval_ok and control_frozen and treatment_frozen):
            break

    control_summary = _summarize_rows(all_control_eval)
    treatment_summary = _summarize_rows(all_treatment_eval)
    paired, paired_rows = _paired_summary(all_control_eval, all_treatment_eval)
    planned_total = a.blocks * a.eval_decks * a.pairs_per_deck * 2

    report = {
        'purpose': 'minimal_chain_context_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'control_policy': 'canonical sparse policy',
        'treatment_policy': 'canonical + phase/turn-side/chain-depth interactions on chain actions only',
        'configuration': {
            'blocks': a.blocks,
            'train_games_per_block_per_arm': a.train_games,
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
            if treatment_summary['learned_win_rate'] is not None and control_summary['learned_win_rate'] is not None
            else None
        ),
        'treatment_minus_control_score_rate': (
            treatment_summary['learned_score_rate'] - control_summary['learned_score_rate']
            if treatment_summary['learned_score_rate'] is not None and control_summary['learned_score_rate'] is not None
            else None
        ),
        'paired_outcomes': paired,
        'paired_results': paired_rows,
        'all_training_complete': all_training_complete,
        'all_evaluation_complete': all_eval_complete,
        'all_policies_frozen': all_frozen,
        'blocks': blocks,
        'note': (
            'Pilot-skill evidence only. Treatment adds no strategic labels or human priors. '
            'Mirror candidate outcomes must not be interpreted as deck rankings.'
        ),
    }
    dump(ROOT/'reports/chain_context_ab.json', report)
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
        raise SystemExit('chain-context A/B training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('chain-context A/B mutated a frozen evaluation policy')
    if not all_eval_complete:
        raise SystemExit('chain-context A/B evaluation did not complete cleanly')
    if control_summary['completed'] != planned_total or treatment_summary['completed'] != planned_total:
        raise SystemExit('chain-context A/B did not complete all planned held-out games')


if __name__ == '__main__':
    main()

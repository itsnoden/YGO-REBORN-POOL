"""Direct held-out duel comparison of two pilot-training regimes.

Control:
- canonical shared-policy training where one policy controls both players.

Treatment:
- one learning seat vs a fixed zero-prior stochastic legal opponent, alternating
  learned seat across training games.

After training, the two frozen policies play each other directly on disjoint
held-out mirror decks with paired seat swaps. This avoids using the stochastic
baseline as the evaluation opponent and therefore tests whether the treatment
actually produces a stronger pilot than the control.

No external strategy priors are used.
"""
from __future__ import annotations

import argparse
import json

from .credit_ab_eval import _block_slice, _train_arm
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .opponent_training_ab_eval import _train_treatment
from .pilot_eval import _usable_candidates
from .pilot_match import evaluate_policy_pair


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
    p.add_argument('--train-seed', type=int, default=391000)
    p.add_argument('--eval-seed', type=int, default=401000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(a.blocks, a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck) < 1:
        raise ValueError('direct opponent-training counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('direct opponent-training requires at least two training decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = (a.block_offset + a.blocks) * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError('not enough usable candidates for direct pilot comparison')

    blocks = []
    all_rows = []
    all_training_complete = True
    all_direct_complete = True

    for block in range(a.blocks):
        cohort_block = a.block_offset + block
        train_pool, eval_pool = _block_slice(
            usable, cohort_block, a.train_decks, a.eval_decks
        )
        control, control_train, control_ok, train_seed, policy_seed = _train_arm(
            a, mapped, train_pool, block, SparsePolicy
        )
        treatment, treatment_train, treatment_ok, t_seed, t_policy_seed = _train_treatment(
            a, mapped, train_pool, block
        )
        if train_seed != t_seed or policy_seed != t_policy_seed:
            raise RuntimeError('direct comparison training seeds diverged')

        direct = {
            'games': 0,
            'completed': 0,
            'a_wins': 0,
            'a_losses': 0,
            'draws': 0,
            'a_score_rate': None,
            'fallback_decisions': 0,
            'all_completed': False,
            'rows': [],
        }
        if control_ok and treatment_ok:
            direct = evaluate_policy_pair(
                a.library, a.database, a.scripts, eval_pool, mapped,
                treatment, control, a.pairs_per_deck,
                a.eval_seed + block * 1000, a.budget,
            )

        block_complete = (
            control_ok and treatment_ok
            and direct['all_completed']
            and direct['fallback_decisions'] == 0
        )
        blocks.append({
            'block': block,
            'candidate_cohort_block': cohort_block,
            'train_candidate_ids': [cid for cid, _ in train_pool],
            'eval_candidate_ids': [cid for cid, _ in eval_pool],
            'train_seed_start': train_seed,
            'eval_seed_start': a.eval_seed + block * 1000,
            'policy_seed': policy_seed,
            'control_training_complete': control_ok,
            'treatment_training_complete': treatment_ok,
            'direct_treatment_vs_control': {
                k: v for k, v in direct.items() if k != 'rows'
            },
            'direct_rows': direct['rows'],
        })
        all_rows.extend(direct['rows'])
        all_training_complete &= control_ok and treatment_ok
        all_direct_complete &= block_complete
        if not block_complete:
            break

    completed = sum(bool(r.get('completed')) for r in all_rows)
    wins = sum(r.get('a_result') == 'win' for r in all_rows)
    losses = sum(r.get('a_result') == 'loss' for r in all_rows)
    draws = sum(r.get('a_result') == 'draw' for r in all_rows)
    planned = a.blocks * a.eval_decks * a.pairs_per_deck * 2
    report = {
        'purpose': 'direct_treatment_vs_control_pilot_duels',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'pilot_skill_evidence': True,
        'control_training': 'shared policy both players',
        'treatment_training': 'one learning seat vs fixed stochastic legal opponent',
        'configuration': {
            'blocks': a.blocks,
            'block_offset': a.block_offset,
            'train_games_per_block': a.train_games,
            'train_decks_per_block': a.train_decks,
            'eval_decks_per_block': a.eval_decks,
            'pairs_per_eval_deck': a.pairs_per_deck,
            'planned_direct_games': planned,
        },
        'training_complete': all_training_complete,
        'direct_games_completed': completed,
        'direct_games_planned': planned,
        'treatment_wins': wins,
        'treatment_losses': losses,
        'draws': draws,
        'treatment_score_rate': (
            (wins + 0.5 * draws) / completed if completed else None
        ),
        'fallback_decisions': sum(
            r.get('fallback_decisions', 0) for r in all_rows
        ),
        'all_direct_complete': all_direct_complete,
        'blocks': blocks,
        'note': (
            'Treatment and control play each other directly on the same held-out '
            'mirror decks with paired seat swaps. This is pilot-skill evidence '
            'only and says nothing about the strength of those decks.'
        ),
    }
    dump(ROOT/'reports/opponent_training_direct.json', report)
    print(json.dumps({
        'completed': completed,
        'planned': planned,
        'treatment_wins': wins,
        'treatment_losses': losses,
        'draws': draws,
        'treatment_score_rate': report['treatment_score_rate'],
        'fallback_decisions': report['fallback_decisions'],
    }))

    if not all_training_complete:
        raise SystemExit('direct pilot comparison training incomplete')
    if not all_direct_complete:
        raise SystemExit('direct pilot comparison incomplete or used fallback')
    if completed != planned:
        raise SystemExit('direct pilot comparison did not complete all games')


if __name__ == '__main__':
    main()

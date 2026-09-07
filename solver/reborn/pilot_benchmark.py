"""Multi-block held-out benchmark for zero-prior Reborn pilot skill.

This benchmark is deliberately isolated from deck ranking. Each block trains a
fresh policy from zero on one generated-candidate slice, freezes it, then tests
against the stochastic legal baseline on different mirror decks and disjoint
seeds with learned-seat swaps. Candidate slices rotate between blocks so one
lucky deck/seed block cannot masquerade as general pilot competence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json

from .import_pool import ROOT, dump
from .learn_probe import run_training_game
from .learning import SparsePolicy
from .oracle import wilson_lower
from .pilot_eval import _usable_candidates, run_eval_game


def _block_slice(usable, block, train_decks, eval_decks):
    width = train_decks + eval_decks
    start = block * width
    stop = start + width
    if stop > len(usable):
        raise RuntimeError(
            f'benchmark block {block} needs candidates [{start}:{stop}], '
            f'but only {len(usable)} usable candidates exist'
        )
    chunk = usable[start:stop]
    return chunk[:train_decks], chunk[train_decks:]


def _train_block(a, mapped, train_pool, block):
    policy_seed = a.policy_seed + block * 100003
    train_seed = a.train_seed + block * 1000
    policy = SparsePolicy(seed=policy_seed, temperature=1.0, learning_rate=0.05)
    rows = []
    for game in range(a.train_games):
        left = game % len(train_pool)
        right = (left + 1) % len(train_pool)
        seat0 = train_pool[left]
        seat1 = train_pool[right]
        if game % 2:
            seat0, seat1 = seat1, seat0
        seed = train_seed + game
        row = {
            'game': game, 'seed': seed,
            'seat0': seat0[0], 'seat1': seat1[0],
        }
        try:
            row.update(run_training_game(
                a.library, a.database, a.scripts,
                (seat0[1], seat1[1]), mapped, policy, seed, a.budget,
            ))
        except Exception as exc:
            row.update(status='blocked', completed=False,
                       blocker=f'{type(exc).__name__}: {exc}')
        rows.append(row)
        if not row.get('completed'):
            break
    complete = len(rows) == a.train_games and all(r.get('completed') for r in rows)
    if not policy.weights:
        complete = False
    return policy, rows, complete, train_seed, policy_seed


def _evaluate_block(a, mapped, eval_pool, policy, block):
    eval_seed = a.eval_seed + block * 1000
    weights_before = dict(policy.weights)
    rows = []
    for deck_index, (candidate_id, deck) in enumerate(eval_pool):
        for pair in range(a.pairs_per_deck):
            seed = eval_seed + deck_index * 100 + pair
            for learned_seat in (0, 1):
                row = {
                    'candidate': candidate_id,
                    'pair': pair,
                    'seed': seed,
                    'learned_seat': learned_seat,
                }
                row.update(run_eval_game(
                    a.library, a.database, a.scripts, deck, mapped,
                    policy, learned_seat, seed, a.budget,
                ))
                rows.append(row)
    return rows, policy.weights == weights_before, eval_seed


def _summarize_rows(rows):
    fallback = Counter(); decisions = Counter()
    for row in rows:
        fallback.update(row.get('fallback_kinds', {}))
        decisions.update(row.get('decision_types', {}))
    return {
        'games': len(rows),
        'completed': sum(bool(r.get('completed')) for r in rows),
        'learned_decisions': sum(r.get('learned_decisions', 0) for r in rows),
        'complex_learned_decisions': sum(r.get('complex_learned_decisions', 0) for r in rows),
        'fallback_decisions': sum(
            r.get('learned_fallback_decisions', r.get('fallback_decisions', 0))
            for r in rows
        ),
        'fallback_kinds': dict(sorted(fallback.items())),
        'observation_checks': sum(r.get('observation_checks', 0) for r in rows),
        'policy_view_checks': sum(r.get('policy_view_checks', 0) for r in rows),
        'decision_types': dict(sorted(decisions.items())),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--blocks', type=int, default=3)
    p.add_argument('--train-games', type=int, default=16)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=6)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=31000)
    p.add_argument('--eval-seed', type=int, default=41000)
    p.add_argument('--policy-seed', type=int, default=20260907)
    a = p.parse_args()

    if min(a.blocks, a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck) < 1:
        raise ValueError('benchmark counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('benchmark requires at least two training decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = a.blocks * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError(f'benchmark needs {needed} usable candidates, found {len(usable)}')

    blocks = []
    all_eval = []
    all_training_complete = True
    all_eval_complete = True
    all_frozen = True

    for block in range(a.blocks):
        train_pool, eval_pool = _block_slice(usable, block, a.train_decks, a.eval_decks)
        policy, train_rows, training_complete, train_seed, policy_seed = _train_block(
            a, mapped, train_pool, block
        )
        eval_rows = []
        frozen = False
        eval_seed = a.eval_seed + block * 1000
        if training_complete:
            eval_rows, frozen, eval_seed = _evaluate_block(a, mapped, eval_pool, policy, block)

        planned_eval = a.eval_decks * a.pairs_per_deck * 2
        eval_complete = (
            len(eval_rows) == planned_eval and
            all(r.get('completed') for r in eval_rows)
        )
        wins = sum(r.get('learned_result') == 'win' for r in eval_rows)
        losses = sum(r.get('learned_result') == 'loss' for r in eval_rows)
        draws = sum(r.get('learned_result') == 'draw' for r in eval_rows)
        complete_eval_count = sum(bool(r.get('completed')) for r in eval_rows)
        rate = wins / complete_eval_count if complete_eval_count else None

        block_row = {
            'block': block,
            'train_candidate_ids': [cid for cid, _ in train_pool],
            'eval_candidate_ids': [cid for cid, _ in eval_pool],
            'train_seed_start': train_seed,
            'eval_seed_start': eval_seed,
            'policy_seed': policy_seed,
            'weight_count': len(policy.weights),
            'training_complete': training_complete,
            'policy_frozen_during_evaluation': frozen,
            'training': _summarize_rows(train_rows),
            'evaluation': {
                **_summarize_rows(eval_rows),
                'planned_games': planned_eval,
                'learned_wins': wins,
                'learned_losses': losses,
                'learned_draws': draws,
                'learned_win_rate': rate,
                'learned_win_wilson95_lower': (
                    wilson_lower(wins, complete_eval_count) if complete_eval_count else None
                ),
            },
            'train_results': train_rows,
            'eval_results': eval_rows,
        }
        blocks.append(block_row)
        all_eval.extend(eval_rows)
        all_training_complete &= training_complete
        all_eval_complete &= eval_complete
        all_frozen &= frozen
        if not training_complete or not eval_complete or not frozen:
            break

    completed = sum(bool(r.get('completed')) for r in all_eval)
    wins = sum(r.get('learned_result') == 'win' for r in all_eval)
    losses = sum(r.get('learned_result') == 'loss' for r in all_eval)
    draws = sum(r.get('learned_result') == 'draw' for r in all_eval)
    rate = wins / completed if completed else None
    planned_total = a.blocks * a.eval_decks * a.pairs_per_deck * 2

    report = {
        'purpose': 'multi_block_heldout_pilot_skill_benchmark_only',
        'profile': 'reborn',
        'policy': 'sparse_softmax_reinforce_v2_complex_actions',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'pilot_skill_evidence': (
            'multi_block_heldout' if all_training_complete and all_eval_complete and all_frozen else False
        ),
        'configuration': {
            'blocks': a.blocks,
            'train_games_per_block': a.train_games,
            'train_decks_per_block': a.train_decks,
            'eval_decks_per_block': a.eval_decks,
            'pairs_per_eval_deck': a.pairs_per_deck,
            'planned_eval_games': planned_total,
            'train_seed_base': a.train_seed,
            'eval_seed_base': a.eval_seed,
            'policy_seed_base': a.policy_seed,
        },
        'aggregate': {
            **_summarize_rows(all_eval),
            'planned_games': planned_total,
            'learned_wins': wins,
            'learned_losses': losses,
            'learned_draws': draws,
            'learned_win_rate': rate,
            'learned_win_wilson95_lower': wilson_lower(wins, completed) if completed else None,
            'all_training_complete': all_training_complete,
            'all_evaluation_complete': all_eval_complete,
            'all_policies_frozen': all_frozen,
        },
        'blocks': blocks,
        'note': (
            'This benchmark measures pilot behavior only. Candidate identities and '
            'mirror outcomes must not be interpreted as deck rankings or fed into '
            'deck search fitness/payoff data.'
        ),
    }
    dump(ROOT/'reports/pilot_benchmark.json', report)
    print(json.dumps({
        'blocks_completed': len(blocks),
        'eval_completed': completed,
        'eval_planned': planned_total,
        'learned_wins': wins,
        'learned_losses': losses,
        'learned_draws': draws,
        'learned_win_rate': rate,
        'wilson95_lower': report['aggregate']['learned_win_wilson95_lower'],
        'fallback_decisions': report['aggregate']['fallback_decisions'],
    }))

    if not all_training_complete:
        raise SystemExit('multi-block benchmark training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('multi-block benchmark mutated a frozen evaluation policy')
    if not all_eval_complete or completed != planned_total:
        raise SystemExit(f'multi-block benchmark completed {completed}/{planned_total} held-out games')


if __name__ == '__main__':
    main()

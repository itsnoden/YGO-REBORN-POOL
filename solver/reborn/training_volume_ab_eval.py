"""Held-out A/B for self-play training volume.

This experiment changes only how many zero-prior self-play training duels the
canonical SparsePolicy receives before a frozen held-out mirror evaluation.

Control: 16 training duels per block.
Treatment: 64 training duels per block.

Within each block, the treatment's first 16 training duels are exactly the same
candidate pairings, seat order, seeds, and policy seed as the control. The
treatment then continues on the same training-candidate cohort with new seeds.
Evaluation uses the same held-out mirror decks, seeds, and learned-seat swaps for
both arms.

No card values, archetype labels, historical/meta data, community opinions, or
human strategy priors are introduced. This is pilot-skill evidence only.
"""
from __future__ import annotations

import argparse
import json

from .credit_ab_eval import _block_slice, _evaluate_arm, _paired_summary, _summarize_rows
from .import_pool import ROOT, dump
from .learn_probe import run_training_game
from .learning import SparsePolicy
from .pilot_eval import _usable_candidates


def training_schedule(train_pool, games, seed_start):
    rows = []
    for game in range(games):
        left = game % len(train_pool)
        right = (left + 1) % len(train_pool)
        seat0 = train_pool[left]
        seat1 = train_pool[right]
        if game % 2:
            seat0, seat1 = seat1, seat0
        rows.append({
            'game': game,
            'seed': seed_start + game,
            'seat0': seat0[0],
            'seat1': seat1[0],
            '_seat0_deck': seat0[1],
            '_seat1_deck': seat1[1],
        })
    return rows


def train_arm(a, mapped, train_pool, block, games):
    policy_seed = a.policy_seed + block * 100003
    train_seed = a.train_seed + block * 1000
    policy = SparsePolicy(seed=policy_seed, temperature=1.0, learning_rate=0.05)
    rows = []
    for plan in training_schedule(train_pool, games, train_seed):
        row = {k: v for k, v in plan.items() if not k.startswith('_')}
        try:
            row.update(run_training_game(
                a.library, a.database, a.scripts,
                (plan['_seat0_deck'], plan['_seat1_deck']),
                mapped, policy, plan['seed'], a.budget,
            ))
        except Exception as exc:
            row.update(
                status='blocked',
                completed=False,
                blocker=f'{type(exc).__name__}: {exc}',
            )
        rows.append(row)
        if not row.get('completed'):
            break
    complete = len(rows) == games and all(r.get('completed') for r in rows)
    if not policy.weights:
        complete = False
    return policy, rows, complete, train_seed, policy_seed


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--blocks', type=int, default=6)
    p.add_argument('--control-train-games', type=int, default=16)
    p.add_argument('--treatment-train-games', type=int, default=64)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=4)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=151000)
    p.add_argument('--eval-seed', type=int, default=161000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(
        a.blocks, a.control_train_games, a.treatment_train_games,
        a.train_decks, a.eval_decks, a.pairs_per_deck
    ) < 1:
        raise ValueError('training-volume A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('training-volume A/B requires at least two training decks')
    if a.treatment_train_games <= a.control_train_games:
        raise ValueError('treatment training volume must exceed control')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = a.blocks * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError(
            f'training-volume A/B needs {needed} usable candidates, found {len(usable)}'
        )

    blocks = []
    all_control_eval = []
    all_treatment_eval = []
    all_training_complete = True
    all_eval_complete = True
    all_frozen = True
    all_prefix_identical = True

    for block in range(a.blocks):
        train_pool, eval_pool = _block_slice(
            usable, block, a.train_decks, a.eval_decks
        )
        control, control_train, control_ok, train_seed, policy_seed = train_arm(
            a, mapped, train_pool, block, a.control_train_games
        )
        treatment, treatment_train, treatment_ok, treatment_seed, treatment_policy_seed = train_arm(
            a, mapped, train_pool, block, a.treatment_train_games
        )
        if train_seed != treatment_seed or policy_seed != treatment_policy_seed:
            raise RuntimeError('training-volume A/B seeds diverged between arms')

        prefix = treatment_train[:len(control_train)]
        prefix_identical = (
            len(prefix) == len(control_train)
            and all(
                c.get('game') == t.get('game')
                and c.get('seed') == t.get('seed')
                and c.get('seat0') == t.get('seat0')
                and c.get('seat1') == t.get('seat1')
                for c, t in zip(control_train, prefix)
            )
        )
        all_prefix_identical &= prefix_identical

        control_eval = []
        treatment_eval = []
        control_frozen = treatment_frozen = False
        eval_seed = a.eval_seed + block * 1000
        if control_ok and treatment_ok:
            control_eval, control_frozen, control_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, control, block
            )
            treatment_eval, treatment_frozen, treatment_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, treatment, block
            )
            if control_eval_seed != treatment_eval_seed:
                raise RuntimeError('training-volume A/B evaluation seeds diverged')
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
            'shared_training_prefix_identical': prefix_identical,
            'control': {
                'training_games': a.control_train_games,
                'weight_count': len(control.weights),
                'training_complete': control_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
            },
            'treatment': {
                'training_games': a.treatment_train_games,
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
            and control_frozen and treatment_frozen and prefix_identical
        ):
            break

    control_summary = _summarize_rows(all_control_eval)
    treatment_summary = _summarize_rows(all_treatment_eval)
    paired, paired_rows = _paired_summary(all_control_eval, all_treatment_eval)
    planned_total = a.blocks * a.eval_decks * a.pairs_per_deck * 2

    report = {
        'purpose': 'self_play_training_volume_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'control_training_games_per_block': a.control_train_games,
        'treatment_training_games_per_block': a.treatment_train_games,
        'treatment_training_multiplier': (
            a.treatment_train_games / a.control_train_games
        ),
        'shared_training_prefix_identical': all_prefix_identical,
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
            'Pilot-skill evidence only. The treatment changes only the amount of '
            'zero-prior self-play training. Held-out mirror outcomes must not be '
            'used as deck rankings.'
        ),
    }
    dump(ROOT/'reports/training_volume_ab.json', report)
    print(json.dumps({
        'blocks_completed': len(blocks),
        'control_train_games': a.control_train_games,
        'treatment_train_games': a.treatment_train_games,
        'shared_prefix_identical': all_prefix_identical,
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

    if not all_prefix_identical:
        raise SystemExit('training-volume A/B shared training prefix diverged')
    if not all_training_complete:
        raise SystemExit('training-volume A/B training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('training-volume A/B mutated a frozen evaluation policy')
    if not all_eval_complete:
        raise SystemExit('training-volume A/B evaluation did not complete cleanly')
    if control_summary['completed'] != planned_total or treatment_summary['completed'] != planned_total:
        raise SystemExit('training-volume A/B did not complete all planned held-out games')


if __name__ == '__main__':
    main()

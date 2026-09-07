"""Held-out A/B for episode-level credit normalization.

This experiment compares the existing zero-prior sparse REINFORCE learner with an
otherwise identical treatment whose terminal episode update gives every duel the
same total nominal credit budget. No card values, archetype labels, human
heuristics, tournament priors, or deck-strength conclusions are introduced.

The control keeps the canonical ``1/sqrt(N)`` per-decision episode scale. The
treatment uses ``1/N`` where ``N`` is the number of learned decisions in the
episode. Training decks, training seeds, policy seeds, evaluation mirror decks,
evaluation seeds, and learned-seat swaps are identical between arms within each
block. The canonical learner is not mutated by this module.
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


class EqualDuelCreditPolicy(SparsePolicy):
    """Experimental policy using equal nominal terminal credit per episode."""

    def update_episode(self, steps, winner, scale=None):
        if scale is None:
            if winner not in (0, 1) or not steps:
                return super().update_episode(steps, winner, scale=scale)
            scale = 1.0 / len(steps)
        return super().update_episode(steps, winner, scale=scale)


def _block_slice(usable, block, train_decks, eval_decks):
    width = train_decks + eval_decks
    start = block * width
    stop = start + width
    if stop > len(usable):
        raise RuntimeError(
            f'credit A/B block {block} needs candidates [{start}:{stop}], '
            f'but only {len(usable)} usable candidates exist'
        )
    chunk = usable[start:stop]
    return chunk[:train_decks], chunk[train_decks:]


def _train_arm(a, mapped, train_pool, block, policy_cls):
    policy_seed = a.policy_seed + block * 100003
    train_seed = a.train_seed + block * 1000
    policy = policy_cls(seed=policy_seed, temperature=1.0, learning_rate=0.05)
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
            'game': game,
            'seed': seed,
            'seat0': seat0[0],
            'seat1': seat1[0],
        }
        try:
            row.update(run_training_game(
                a.library, a.database, a.scripts,
                (seat0[1], seat1[1]), mapped, policy, seed, a.budget,
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
    complete = len(rows) == a.train_games and all(r.get('completed') for r in rows)
    if not policy.weights:
        complete = False
    return policy, rows, complete, train_seed, policy_seed


def _evaluate_arm(a, mapped, eval_pool, policy, block):
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
    fallback = Counter()
    decisions = Counter()
    for row in rows:
        fallback.update(row.get('fallback_kinds', {}))
        decisions.update(row.get('decision_types', {}))
    completed = sum(bool(r.get('completed')) for r in rows)
    wins = sum(r.get('learned_result') == 'win' for r in rows)
    losses = sum(r.get('learned_result') == 'loss' for r in rows)
    draws = sum(r.get('learned_result') == 'draw' for r in rows)
    return {
        'games': len(rows),
        'completed': completed,
        'learned_wins': wins,
        'learned_losses': losses,
        'learned_draws': draws,
        'learned_win_rate': wins / completed if completed else None,
        'learned_score_rate': (wins + 0.5 * draws) / completed if completed else None,
        'learned_win_wilson95_lower': wilson_lower(wins, completed) if completed else None,
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


def _result_value(row):
    return {'loss': 0.0, 'draw': 0.5, 'win': 1.0}.get(row.get('learned_result'))


def _paired_summary(control_rows, treatment_rows):
    if len(control_rows) != len(treatment_rows):
        raise RuntimeError('credit A/B arms produced different evaluation lengths')
    improved = degraded = unchanged = unavailable = 0
    pairs = []
    keys = ('candidate', 'pair', 'seed', 'learned_seat')
    for control, treatment in zip(control_rows, treatment_rows):
        if any(control.get(k) != treatment.get(k) for k in keys):
            raise RuntimeError('credit A/B evaluation rows are misaligned')
        c = _result_value(control)
        t = _result_value(treatment)
        if c is None or t is None:
            outcome = 'unavailable'
            unavailable += 1
        elif t > c:
            outcome = 'improved'
            improved += 1
        elif t < c:
            outcome = 'degraded'
            degraded += 1
        else:
            outcome = 'unchanged'
            unchanged += 1
        pairs.append({
            **{k: control.get(k) for k in keys},
            'control_result': control.get('learned_result'),
            'treatment_result': treatment.get('learned_result'),
            'paired_outcome': outcome,
        })
    return {
        'improved': improved,
        'degraded': degraded,
        'unchanged': unchanged,
        'unavailable': unavailable,
    }, pairs


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
    p.add_argument('--train-seed', type=int, default=81000)
    p.add_argument('--eval-seed', type=int, default=91000)
    p.add_argument('--policy-seed', type=int, default=20260907)
    a = p.parse_args()

    if min(a.blocks, a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck) < 1:
        raise ValueError('credit A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('credit A/B requires at least two training decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = a.blocks * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError(f'credit A/B needs {needed} usable candidates, found {len(usable)}')

    block_reports = []
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
            a, mapped, train_pool, block, EqualDuelCreditPolicy
        )
        if train_seed != treatment_train_seed or policy_seed != treatment_policy_seed:
            raise RuntimeError('credit A/B training seeds diverged between arms')

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
                raise RuntimeError('credit A/B evaluation seeds diverged between arms')
            eval_seed = control_eval_seed

        planned = a.eval_decks * a.pairs_per_deck * 2
        control_eval_ok = len(control_eval) == planned and all(r.get('completed') for r in control_eval)
        treatment_eval_ok = len(treatment_eval) == planned and all(r.get('completed') for r in treatment_eval)
        paired, pair_rows = _paired_summary(control_eval, treatment_eval)

        block_reports.append({
            'block': block,
            'train_candidate_ids': [cid for cid, _ in train_pool],
            'eval_candidate_ids': [cid for cid, _ in eval_pool],
            'train_seed_start': train_seed,
            'eval_seed_start': eval_seed,
            'policy_seed': policy_seed,
            'control': {
                'normalization': 'canonical_1_over_sqrt_N',
                'weight_count': len(control.weights),
                'training_complete': control_train_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
                'train_results': control_train,
                'eval_results': control_eval,
            },
            'treatment': {
                'normalization': 'equal_total_credit_1_over_N',
                'weight_count': len(treatment.weights),
                'training_complete': treatment_train_ok,
                'policy_frozen_during_evaluation': treatment_frozen,
                'training': _summarize_rows(treatment_train),
                'evaluation': _summarize_rows(treatment_eval),
                'train_results': treatment_train,
                'eval_results': treatment_eval,
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
        'purpose': 'episode_credit_normalization_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'control_normalization': '1/sqrt(N) per learned decision',
        'treatment_normalization': '1/N per learned decision',
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
        'blocks': block_reports,
        'note': (
            'This is pilot-skill A/B evidence only. The two arms use identical candidate '
            'slices and seeds; only terminal episode credit normalization differs. Do not '
            'interpret mirror candidate results as deck rankings.'
        ),
    }
    dump(ROOT/'reports/credit_normalization_ab.json', report)
    print(json.dumps({
        'blocks_completed': len(block_reports),
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
        raise SystemExit('episode-credit A/B training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('episode-credit A/B mutated a frozen evaluation policy')
    if not all_eval_complete:
        raise SystemExit('episode-credit A/B evaluation did not complete cleanly')
    if control_summary['completed'] != planned_total or treatment_summary['completed'] != planned_total:
        raise SystemExit(
            f'episode-credit A/B completed control={control_summary["completed"]}, '
            f'treatment={treatment_summary["completed"]}, planned={planned_total}'
        )


if __name__ == '__main__':
    main()

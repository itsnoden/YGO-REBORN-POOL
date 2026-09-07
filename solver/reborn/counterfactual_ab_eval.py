"""Preliminary held-out A/B test for offline counterfactual pilot training.

Both policies receive the exact same ordinary zero-prior self-play training.
Only the treatment policy then receives simulator-labeled counterfactual updates
from disjoint training seeds/decks.  Both frozen policies are evaluated on the
same held-out mirror decks, seeds and learned-seat swaps against the same
zero-prior stochastic legal baseline.

This measures pilot behavior only.  Candidate identities and outcomes must not
be interpreted as deck rankings or deck-strength evidence.
"""
from __future__ import annotations

import argparse
import json
import random

from .counterfactual_train_probe import _branchable_indices, _train_target
from .import_pool import ROOT, dump
from .learn_probe import run_training_game
from .learning import SparsePolicy
from .oracle import wilson_lower
from .pilot_eval import _usable_candidates, run_eval_game


def _ordinary_train(a, mapped, train_pool):
    policy = SparsePolicy(seed=a.policy_seed, temperature=1.0, learning_rate=0.05)
    rows = []
    for game in range(a.train_games):
        left = game % len(train_pool)
        right = (left + 1) % len(train_pool)
        seat0, seat1 = train_pool[left], train_pool[right]
        if game % 2:
            seat0, seat1 = seat1, seat0
        seed = a.train_seed + game
        row = {'game': game, 'seed': seed, 'seat0': seat0[0], 'seat1': seat1[0]}
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
    return policy, rows, complete


def _counterfactual_stage(a, policy, mapped, train_pool):
    from .replay_probe import _record_game

    rows = []
    for source_index in range(a.cf_sources):
        candidate_id, deck = train_pool[source_index % len(train_pool)]
        seed = a.cf_seed + source_index
        source = {
            'source_index': source_index,
            'candidate': candidate_id,
            'seed': seed,
            'status': 'pending',
        }
        try:
            recorded = _record_game(
                a.library, a.database, a.scripts, seed, deck, mapped, a.budget
            )
            candidates = _branchable_indices(recorded['history'], a.cf_max_options)
            if not candidates:
                raise RuntimeError('counterfactual source duel has no bounded explicit targets')
            rng = random.Random(a.policy_seed ^ seed ^ 0xC0FFEE)
            rng.shuffle(candidates)
            selected = sorted(candidates[:a.cf_targets])
            target_rows = [
                _train_target(
                    policy, a.library, a.database, a.scripts, seed, deck, mapped,
                    recorded['history'], target_index, a.budget, a.cf_rollouts,
                    a.cf_continuation_seed + source_index * 100000,
                )
                for target_index in selected
            ]
            source.update(
                status='completed', completed=True,
                source_winner_debug_only=recorded['winner'],
                source_decisions=len(recorded['history']),
                branchable_targets=len(candidates),
                selected_targets=selected,
                targets=target_rows,
                preference_updates=sum(row['updated'] for row in target_rows),
            )
        except Exception as exc:
            source.update(status='blocked', completed=False,
                          blocker=f'{type(exc).__name__}: {exc}')
        rows.append(source)
        if not source.get('completed'):
            break
    complete = len(rows) == a.cf_sources and all(r.get('completed') for r in rows)
    return rows, complete


def _evaluate(a, mapped, eval_pool, policy):
    before = dict(policy.weights)
    rows = []
    for deck_index, (candidate_id, deck) in enumerate(eval_pool):
        for pair in range(a.pairs_per_deck):
            seed = a.eval_seed + deck_index * 100 + pair
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
    frozen = policy.weights == before
    return rows, frozen


def _summary(rows):
    completed = sum(bool(r.get('completed')) for r in rows)
    wins = sum(r.get('learned_result') == 'win' for r in rows)
    losses = sum(r.get('learned_result') == 'loss' for r in rows)
    draws = sum(r.get('learned_result') == 'draw' for r in rows)
    return {
        'games': len(rows),
        'completed': completed,
        'wins': wins,
        'losses': losses,
        'draws': draws,
        'win_rate': wins / completed if completed else None,
        'wilson95_lower': wilson_lower(wins, completed) if completed else None,
        'fallback_decisions': sum(r.get('learned_fallback_decisions', 0) for r in rows),
        'observation_checks': sum(r.get('observation_checks', 0) for r in rows),
        'policy_view_checks': sum(r.get('policy_view_checks', 0) for r in rows),
    }


def _paired_delta(control_rows, treatment_rows):
    if len(control_rows) != len(treatment_rows):
        raise ValueError('A/B evaluation row counts differ')
    improved = degraded = unchanged = 0
    value = {'loss': -1, 'draw': 0, 'win': 1}
    for control, treatment in zip(control_rows, treatment_rows):
        key_c = (control.get('candidate'), control.get('pair'), control.get('seed'), control.get('learned_seat'))
        key_t = (treatment.get('candidate'), treatment.get('pair'), treatment.get('seed'), treatment.get('learned_seat'))
        if key_c != key_t:
            raise ValueError('A/B evaluation pairing mismatch')
        c = value.get(control.get('learned_result'))
        t = value.get(treatment.get('learned_result'))
        if c is None or t is None:
            continue
        if t > c:
            improved += 1
        elif t < c:
            degraded += 1
        else:
            unchanged += 1
    return {'improved': improved, 'degraded': degraded, 'unchanged': unchanged}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--train-games', type=int, default=16)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=4)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=71000)
    p.add_argument('--cf-seed', type=int, default=72000)
    p.add_argument('--eval-seed', type=int, default=73000)
    p.add_argument('--policy-seed', type=int, default=20260907)
    p.add_argument('--cf-sources', type=int, default=2)
    p.add_argument('--cf-targets', type=int, default=2)
    p.add_argument('--cf-max-options', type=int, default=3)
    p.add_argument('--cf-rollouts', type=int, default=3)
    p.add_argument('--cf-continuation-seed', type=int, default=74000)
    a = p.parse_args()

    if min(a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck,
           a.cf_sources, a.cf_targets, a.cf_rollouts) < 1:
        raise ValueError('A/B counts must be positive')
    if a.train_decks < 2 or a.cf_max_options < 2:
        raise ValueError('A/B requires >=2 train decks and cf-max-options >=2')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    required = a.train_decks + a.eval_decks
    if len(usable) < required:
        raise RuntimeError(f'A/B needs {required} usable candidates, found {len(usable)}')
    train_pool = usable[:a.train_decks]
    eval_pool = usable[a.train_decks:required]

    base, train_rows, training_complete = _ordinary_train(a, mapped, train_pool)
    control = SparsePolicy(
        seed=a.policy_seed + 1, temperature=base.temperature,
        learning_rate=base.learning_rate, weights=dict(base.weights),
    )
    treatment = SparsePolicy(
        seed=a.policy_seed + 2, temperature=base.temperature,
        learning_rate=base.learning_rate, weights=dict(base.weights),
    )

    cf_rows = []
    cf_complete = False
    if training_complete:
        cf_rows, cf_complete = _counterfactual_stage(a, treatment, mapped, train_pool)
    cf_updates = sum(r.get('preference_updates', 0) for r in cf_rows)

    control_rows = treatment_rows = []
    control_frozen = treatment_frozen = False
    if training_complete and cf_complete:
        control_rows, control_frozen = _evaluate(a, mapped, eval_pool, control)
        treatment_rows, treatment_frozen = _evaluate(a, mapped, eval_pool, treatment)

    control_summary = _summary(control_rows)
    treatment_summary = _summary(treatment_rows)
    planned = a.eval_decks * a.pairs_per_deck * 2
    paired = _paired_delta(control_rows, treatment_rows) if control_rows and treatment_rows else {
        'improved': 0, 'degraded': 0, 'unchanged': 0,
    }
    delta = None
    if control_summary['win_rate'] is not None and treatment_summary['win_rate'] is not None:
        delta = treatment_summary['win_rate'] - control_summary['win_rate']

    control.save(ROOT/'reports/counterfactual_ab_control_policy.json')
    treatment.save(ROOT/'reports/counterfactual_ab_treatment_policy.json')
    report = {
        'purpose': 'counterfactual_training_heldout_pilot_ab_only',
        'deck_strength_evidence': False,
        'deck_ranking_evidence': False,
        'pilot_skill_evidence': 'preliminary_ab' if (
            training_complete and cf_complete and
            control_summary['completed'] == planned and
            treatment_summary['completed'] == planned and
            control_frozen and treatment_frozen
        ) else False,
        'external_strategy_priors': False,
        'live_rollout_policy': False,
        'hidden_state_used_as_policy_feature': False,
        'configuration': {
            'train_games': a.train_games,
            'train_decks': a.train_decks,
            'eval_decks': a.eval_decks,
            'pairs_per_deck': a.pairs_per_deck,
            'planned_eval_games_per_arm': planned,
            'cf_sources': a.cf_sources,
            'cf_targets_per_source': a.cf_targets,
            'cf_max_options': a.cf_max_options,
            'cf_rollouts_per_option': a.cf_rollouts,
            'train_seed': a.train_seed,
            'cf_seed': a.cf_seed,
            'eval_seed': a.eval_seed,
        },
        'ordinary_training_complete': training_complete,
        'ordinary_training_games': len(train_rows),
        'ordinary_weight_count': len(base.weights),
        'counterfactual_training_complete': cf_complete,
        'counterfactual_preference_updates': cf_updates,
        'treatment_weight_count': len(treatment.weights),
        'control': control_summary,
        'treatment': treatment_summary,
        'treatment_minus_control_win_rate': delta,
        'paired_outcomes': paired,
        'control_policy_frozen': control_frozen,
        'treatment_policy_frozen': treatment_frozen,
        'train_candidate_ids': [cid for cid, _ in train_pool],
        'eval_candidate_ids': [cid for cid, _ in eval_pool],
        'counterfactual_sources': cf_rows,
        'ordinary_train_results': train_rows,
        'control_eval_results': control_rows,
        'treatment_eval_results': treatment_rows,
        'note': (
            'Both arms start from identical ordinary training weights. Only the treatment arm receives '
            'offline simulator-labeled counterfactual updates. Held-out mirror decks, disjoint seeds and '
            'seat swaps measure pilot behavior only; no deck-strength conclusion is authorized.'
        ),
    }
    dump(ROOT/'reports/counterfactual_ab_eval.json', report)
    print(json.dumps({
        'ordinary_training_complete': training_complete,
        'cf_complete': cf_complete,
        'cf_updates': cf_updates,
        'control_completed': control_summary['completed'],
        'control_wins': control_summary['wins'],
        'treatment_completed': treatment_summary['completed'],
        'treatment_wins': treatment_summary['wins'],
        'delta_win_rate': delta,
        'paired': paired,
    }))

    if not training_complete:
        raise SystemExit('counterfactual A/B ordinary training did not complete')
    if not cf_complete:
        raise SystemExit('counterfactual A/B treatment stage did not complete')
    if cf_updates <= 0:
        raise SystemExit('counterfactual A/B produced no preference updates')
    if not control_frozen or not treatment_frozen:
        raise SystemExit('counterfactual A/B evaluation mutated a frozen policy')
    if control_summary['completed'] != planned or treatment_summary['completed'] != planned:
        raise SystemExit('counterfactual A/B held-out evaluation did not complete')


if __name__ == '__main__':
    main()

"""Exploratory duel-guided challenger screen for YGO Reborn.

This module turns actual paired-seat duel outcomes into a search signal without
claiming final deck strength.  It trains one universal zero-prior pilot on a
separate cohort, generates legal challengers only through algorithmic mutation /
crossover, and evaluates each challenger against a fixed adversary set in both
seat orientations on matched seeds.

No historical deck lists, card values, archetype labels, tier lists, community
opinions, or human strategy priors enter challenger generation or evaluation.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random

from .import_pool import ROOT, dump
from .oracle import wilson_lower
from .payoff_matrix_eval import (
    POLICIES, run_frozen_policy_duel, train_universal_policy, usable_candidates,
)
from .search import crossover, mutate, validate


def deck_id(deck):
    return hashlib.sha256('|'.join(sorted(deck)).encode()).hexdigest()[:16]


def generate_challengers(adversaries, cards, count, seed):
    rng = random.Random(seed)
    generated = {}
    parents = [deck for _, deck in adversaries]
    cursor = 0
    while len(generated) < count:
        mode = cursor % 3
        if mode == 0:
            parent = parents[cursor % len(parents)]
            deck = mutate(parent, cards, rng, 1)
            method = 'one_card_mutation'
        elif mode == 1:
            parent = parents[cursor % len(parents)]
            deck = mutate(parent, cards, rng, 2)
            method = 'two_card_mutation'
        else:
            a = parents[cursor % len(parents)]
            b = parents[(cursor + 1) % len(parents)]
            deck = crossover(a, b, cards, rng)
            method = 'crossover'
        validate(deck, cards)
        cid = deck_id(deck)
        if cid not in generated and all(tuple(sorted(deck)) != tuple(sorted(p)) for p in parents):
            generated[cid] = {'deck': list(deck), 'method': method}
        cursor += 1
        if cursor > count * 100:
            raise RuntimeError('unable to generate enough unique legal challengers')
    return generated


def evaluate_challenger(a, mapped, policy, challenger_id, challenger, adversaries):
    rows = []
    per_opponent = {}
    for opp_index, (opp_id, opp_deck) in enumerate(adversaries):
        sample = {
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'games': 0,
            'unsupported': 0,
            'timeouts': 0,
            'fallback_decisions': 0,
        }
        for pair in range(a.seeds_per_opponent):
            seed = a.eval_seed + opp_index * 1000 + pair

            # Challenger first.
            first = run_frozen_policy_duel(
                a.library, a.database, a.scripts,
                (challenger, opp_deck), mapped, policy, seed, a.budget,
            )
            rows.append({
                'challenger': challenger_id,
                'opponent': opp_id,
                'pair': pair,
                'seed': seed,
                'challenger_seat': 0,
                'result': first,
            })
            _accumulate(sample, first, 0)

            # Challenger second, same duel seed.
            second = run_frozen_policy_duel(
                a.library, a.database, a.scripts,
                (opp_deck, challenger), mapped, policy, seed, a.budget,
            )
            rows.append({
                'challenger': challenger_id,
                'opponent': opp_id,
                'pair': pair,
                'seed': seed,
                'challenger_seat': 1,
                'result': second,
            })
            _accumulate(sample, second, 1)

        completed = sample['games'] - sample['unsupported']
        sample['win_rate'] = sample['wins'] / completed if completed else None
        sample['score_rate'] = (
            (sample['wins'] + 0.5 * sample['draws']) / completed
            if completed else None
        )
        sample['win_wilson95_lower'] = (
            wilson_lower(sample['wins'], completed) if completed else None
        )
        sample['certified'] = bool(
            completed == sample['games']
            and sample['games'] > 0
            and sample['timeouts'] == 0
            and sample['fallback_decisions'] == 0
        )
        per_opponent[opp_id] = sample

    all_samples = list(per_opponent.values())
    certified = bool(all_samples) and all(s['certified'] for s in all_samples)
    aggregate = {
        'games': sum(s['games'] for s in all_samples),
        'wins': sum(s['wins'] for s in all_samples),
        'losses': sum(s['losses'] for s in all_samples),
        'draws': sum(s['draws'] for s in all_samples),
        'unsupported': sum(s['unsupported'] for s in all_samples),
        'timeouts': sum(s['timeouts'] for s in all_samples),
        'fallback_decisions': sum(s['fallback_decisions'] for s in all_samples),
        'certified': certified,
        'worst_opponent_win_wilson95_lower': (
            min(s['win_wilson95_lower'] for s in all_samples)
            if certified else None
        ),
        'mean_score_rate': (
            sum(s['score_rate'] for s in all_samples) / len(all_samples)
            if certified else None
        ),
    }
    return per_opponent, aggregate, rows


def _accumulate(sample, result, challenger_seat):
    sample['games'] += 1
    sample['fallback_decisions'] += int(result.get('fallback_decisions', 0))
    if not result.get('completed'):
        sample['unsupported'] += 1
        if result.get('blocker') and 'exceeded' in result['blocker']:
            sample['timeouts'] += 1
        return
    winner = result.get('winner')
    if winner not in (0, 1):
        sample['draws'] += 1
    elif winner == challenger_seat:
        sample['wins'] += 1
    else:
        sample['losses'] += 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--policy', choices=sorted(POLICIES), default='chain_context')
    p.add_argument('--train-games', type=int, default=64)
    p.add_argument('--train-decks', type=int, default=8)
    p.add_argument('--adversaries', type=int, default=4)
    p.add_argument('--challengers', type=int, default=8)
    p.add_argument('--seeds-per-opponent', type=int, default=2)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=271000)
    p.add_argument('--eval-seed', type=int, default=281000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    p.add_argument('--mutation-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(
        a.train_games, a.train_decks, a.adversaries,
        a.challengers, a.seeds_per_opponent
    ) < 1:
        raise ValueError('challenger-screen sizes must all be positive')
    if a.train_decks < 2:
        raise ValueError('challenger-screen training requires at least two decks')

    all_cards = json.loads((ROOT/'data/processed/cards.json').read_text())
    cards = {
        c['id']: c for c in all_cards
        if c['legal'] and c['placement'] == 'main'
    }
    mapped = {
        r['reborn_id']: r
        for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    }
    usable = usable_candidates(
        {c['id']: c for c in all_cards},
        mapped,
    )
    required = a.train_decks + a.adversaries
    if len(usable) < required:
        raise RuntimeError(
            f'challenger screen needs {required} usable candidates, found {len(usable)}'
        )

    train_pool = usable[:a.train_decks]
    adversaries = usable[a.train_decks:required]
    policy_cls = POLICIES[a.policy]
    policy, training, training_complete = train_universal_policy(
        a, mapped, train_pool, policy_cls
    )

    challengers = {}
    evaluations = {}
    duel_rows = []
    if training_complete:
        challengers = generate_challengers(
            adversaries, cards, a.challengers, a.mutation_seed
        )
        for challenger_id, spec in challengers.items():
            per_opp, aggregate, rows = evaluate_challenger(
                a, mapped, policy, challenger_id, spec['deck'], adversaries
            )
            evaluations[challenger_id] = {
                'method': spec['method'],
                'main': dict(collections.Counter(spec['deck'])),
                'per_opponent': per_opp,
                'aggregate': aggregate,
            }
            duel_rows.extend(rows)

    certified_ids = [
        cid for cid, row in evaluations.items()
        if row['aggregate']['certified']
    ]
    exploratory_best = None
    if certified_ids:
        exploratory_best = max(
            certified_ids,
            key=lambda cid: (
                evaluations[cid]['aggregate']['worst_opponent_win_wilson95_lower'],
                evaluations[cid]['aggregate']['mean_score_rate'],
                cid,
            ),
        )

    report = {
        'purpose': 'exploratory_duel_guided_best_response_screen',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'pilot_model': a.policy,
        'pilot_skill_certified_for_ranking': False,
        'deck_ranking_evidence': False,
        'training_complete': training_complete,
        'training_candidate_ids': [cid for cid, _ in train_pool],
        'adversary_candidate_ids': [cid for cid, _ in adversaries],
        'generated_challengers': len(challengers),
        'evaluated_challengers': len(evaluations),
        'seeds_per_opponent': a.seeds_per_opponent,
        'planned_duels': (
            len(challengers) * len(adversaries) * a.seeds_per_opponent * 2
        ),
        'completed_duels': sum(
            bool(row['result'].get('completed')) for row in duel_rows
        ),
        'exploratory_best_response_only': exploratory_best,
        'evaluations': evaluations,
        'duel_rows': duel_rows,
        'note': (
            'Actual paired-seat duel outcomes drive this challenger screen, but '
            'the pilot is not yet promoted for final ranking. The exploratory '
            'best-response field must not be called the strongest deck.'
        ),
    }
    dump(ROOT/'reports/challenger_screen.json', report)
    print(json.dumps({
        'policy': a.policy,
        'training_complete': training_complete,
        'adversaries': len(adversaries),
        'challengers': len(challengers),
        'planned_duels': report['planned_duels'],
        'completed_duels': report['completed_duels'],
        'exploratory_best_response_only': exploratory_best,
        'deck_ranking_evidence': False,
    }))

    if not training_complete:
        raise SystemExit('challenger-screen pilot training did not complete')
    if report['completed_duels'] != report['planned_duels']:
        raise SystemExit('challenger screen did not complete all planned duels')


if __name__ == '__main__':
    main()

"""Exploratory iterative duel-guided best-response search.

This is the first multi-round search loop driven by actual paired-seat duel
outcomes rather than static proxy scores.

Each round:
1. start from the current adversary population;
2. generate legal challengers using card mutations, crossover, duplicate
   consolidation, and neutral rule-text relation proposals;
3. test every challenger against every current adversary in both seat
   orientations on matched seeds;
4. select the challenger with the strongest conservative worst-opponent result;
5. add it to the adversary population and repeat.

The pilot remains explicitly exploratory until a separate pilot-skill treatment
is certified. Therefore no output of this module may be called the strongest
deck. Its purpose is to validate the adversarial search machinery and discover
candidate regions worth retesting once the pilot gate is satisfied.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random

from .challenger_screen import evaluate_challenger
from .import_pool import ROOT, dump
from .payoff_matrix_eval import POLICIES, train_universal_policy, usable_candidates
from .search import crossover, mutate, validate
from .structural_mutation import duplicate_consolidation, relation_pair_injection


def identity(deck):
    return hashlib.sha256('|'.join(sorted(deck)).encode()).hexdigest()[:16]


def _legal_main_cards():
    rows = json.loads((ROOT/'data/processed/cards.json').read_text())
    return {
        c['id']: c for c in rows
        if c['legal'] and c['placement'] == 'main'
    }, {c['id']: c for c in rows}


def generate_round_challengers(
    population, cards, graph, count, seed,
):
    rng = random.Random(seed)
    parents = list(population)
    generated = {}
    cursor = 0

    while len(generated) < count:
        parent_id, parent = parents[cursor % len(parents)]
        mode = cursor % 5
        meta = {'parent': parent_id}
        try:
            if mode == 0:
                deck = mutate(parent, cards, rng, 1)
                meta['method'] = 'one_card_mutation'
            elif mode == 1:
                deck = mutate(parent, cards, rng, 2)
                meta['method'] = 'two_card_mutation'
            elif mode == 2:
                other_id, other = parents[(cursor + 1) % len(parents)]
                deck = crossover(parent, other, cards, rng)
                meta.update(method='crossover', other_parent=other_id)
            elif mode == 3:
                deck, structural = duplicate_consolidation(
                    parent, cards, rng
                )
                meta.update(structural)
            else:
                deck, structural = relation_pair_injection(
                    parent, cards, graph, rng, desired_each=2
                )
                meta.update(structural)
        except ValueError:
            cursor += 1
            if cursor > count * 500:
                raise RuntimeError('unable to generate iterative challengers')
            continue

        deck = tuple(sorted(deck))
        validate(list(deck), cards)
        cid = identity(deck)
        if cid not in {pid for pid, _ in population} and cid not in generated:
            generated[cid] = {
                'id': cid,
                'deck': list(deck),
                **meta,
            }

        cursor += 1
        if cursor > count * 500:
            raise RuntimeError('unable to generate enough unique challengers')

    return list(generated.values())


def challenger_key(row):
    agg = row['aggregate']
    return (
        agg['worst_opponent_win_wilson95_lower'],
        agg['mean_score_rate'],
        agg['wins'] - agg['losses'],
        row['id'],
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--policy', choices=sorted(POLICIES), default='canonical')
    p.add_argument('--train-games', type=int, default=64)
    p.add_argument('--train-decks', type=int, default=8)
    p.add_argument('--initial-population', type=int, default=4)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--challengers-per-round', type=int, default=6)
    p.add_argument('--seeds-per-opponent', type=int, default=2)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=471000)
    p.add_argument('--eval-seed', type=int, default=481000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    p.add_argument('--mutation-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(
        a.train_games, a.train_decks, a.initial_population,
        a.rounds, a.challengers_per_round, a.seeds_per_opponent
    ) < 1:
        raise ValueError('iterative-search counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('iterative search requires at least two training decks')

    legal_main, cards_by_id = _legal_main_cards()
    mapped = {
        row['reborn_id']: row
        for row in json.loads(
            (ROOT/'data/processed/engine_cards.json').read_text()
        )
    }
    graph = json.loads(
        (ROOT/'data/processed/synergy_graph.json').read_text()
    )
    usable = usable_candidates(cards_by_id, mapped)

    required = a.train_decks + a.initial_population
    if len(usable) < required:
        raise RuntimeError(
            f'iterative search needs {required} usable candidates'
        )

    train_pool = usable[:a.train_decks]
    population = list(usable[a.train_decks:required])

    policy_cls = POLICIES[a.policy]
    policy, training, training_complete = train_universal_policy(
        a, mapped, train_pool, policy_cls
    )

    rounds = []
    total_duels = 0
    total_completed = 0

    if training_complete:
        for round_index in range(a.rounds):
            proposals = generate_round_challengers(
                population,
                legal_main,
                graph,
                a.challengers_per_round,
                a.mutation_seed + round_index * 100003,
            )

            evaluated = []
            for proposal_index, proposal in enumerate(proposals):
                # Offset each challenger into a disjoint seed band while keeping
                # matched seats within its own adversary comparisons.
                local = argparse.Namespace(**vars(a))
                local.eval_seed = (
                    a.eval_seed
                    + round_index * 100000
                    + proposal_index * 10000
                )
                per_opp, aggregate, duel_rows = evaluate_challenger(
                    local, mapped, policy,
                    proposal['id'], proposal['deck'], population,
                )
                total_duels += len(duel_rows)
                total_completed += sum(
                    bool(row['result'].get('completed'))
                    for row in duel_rows
                )
                evaluated.append({
                    **proposal,
                    'per_opponent': per_opp,
                    'aggregate': aggregate,
                    'duel_rows': duel_rows,
                })

            certified = [
                row for row in evaluated
                if row['aggregate']['certified']
            ]
            if not certified:
                rounds.append({
                    'round': round_index,
                    'population_before': [cid for cid, _ in population],
                    'evaluated': evaluated,
                    'selected_challenger': None,
                    'status': 'no_certified_challenger',
                })
                break

            selected = max(certified, key=challenger_key)
            population.append(
                (selected['id'], selected['deck'])
            )

            rounds.append({
                'round': round_index,
                'population_before': [
                    cid for cid, _ in population[:-1]
                ],
                'evaluated': evaluated,
                'selected_challenger': selected['id'],
                'selected_method': selected['method'],
                'selected_aggregate': selected['aggregate'],
                'population_after': [cid for cid, _ in population],
                'status': 'completed',
            })

    report = {
        'purpose': 'exploratory_iterative_duel_guided_best_response_search',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'pilot_model': a.policy,
        'pilot_skill_certified_for_ranking': False,
        'deck_ranking_evidence': False,
        'training_complete': training_complete,
        'training_candidate_ids': [cid for cid, _ in train_pool],
        'initial_population_ids': [
            cid for cid, _ in usable[
                a.train_decks:a.train_decks + a.initial_population
            ]
        ],
        'rounds_requested': a.rounds,
        'rounds_completed': sum(
            row.get('status') == 'completed'
            for row in rounds
        ),
        'challengers_per_round': a.challengers_per_round,
        'seeds_per_opponent': a.seeds_per_opponent,
        'total_duels': total_duels,
        'completed_duels': total_completed,
        'final_population_ids': [cid for cid, _ in population],
        'rounds': rounds,
        'note': (
            'This is exploratory search infrastructure. Real paired-seat duel '
            'outcomes drive every promotion, but the pilot is not yet certified '
            'for final deck ranking. Selected challengers are investigation '
            'candidates, not strongest-deck claims.'
        ),
    }
    dump(ROOT/'reports/iterative_challenger_search.json', report)
    print(json.dumps({
        'training_complete': training_complete,
        'rounds_completed': report['rounds_completed'],
        'total_duels': total_duels,
        'completed_duels': total_completed,
        'final_population': report['final_population_ids'],
        'deck_ranking_evidence': False,
    }))

    if not training_complete:
        raise SystemExit('iterative search pilot training incomplete')
    if total_completed != total_duels:
        raise SystemExit('iterative search had incomplete duels')
    if report['rounds_completed'] != a.rounds:
        raise SystemExit('iterative search stopped before all requested rounds')


if __name__ == '__main__':
    main()

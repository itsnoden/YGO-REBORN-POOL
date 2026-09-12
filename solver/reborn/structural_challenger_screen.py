"""Exploratory duel screen for zero-prior structural deck mutations.

This tests whether copy-consolidation and text-relation proposal operators can
produce useful legal challengers from the existing generated candidate pool.
Actual paired-seat duel outcomes are recorded, but final deck ranking remains
disabled until pilot competence is separately certified.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json

from .challenger_screen import evaluate_challenger
from .import_pool import ROOT, dump
from .payoff_matrix_eval import POLICIES, train_universal_policy, usable_candidates
from .structural_mutation import generate_structural_challengers


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--policy', choices=sorted(POLICIES), default='canonical')
    p.add_argument('--train-games', type=int, default=64)
    p.add_argument('--train-decks', type=int, default=8)
    p.add_argument('--adversaries', type=int, default=4)
    p.add_argument('--challengers', type=int, default=6)
    p.add_argument('--seeds-per-opponent', type=int, default=2)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=351000)
    p.add_argument('--eval-seed', type=int, default=361000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    p.add_argument('--mutation-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(
        a.train_games, a.train_decks, a.adversaries,
        a.challengers, a.seeds_per_opponent
    ) < 1:
        raise ValueError('structural screen sizes must all be positive')
    if a.train_decks < 2:
        raise ValueError('structural screen training requires at least two decks')

    all_cards = json.loads((ROOT/'data/processed/cards.json').read_text())
    cards_by_id = {c['id']: c for c in all_cards}
    legal_main = {
        c['id']: c for c in all_cards
        if c['legal'] and c['placement'] == 'main'
    }
    mapped = {
        r['reborn_id']: r
        for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    }
    graph = json.loads((ROOT/'data/processed/synergy_graph.json').read_text())
    usable = usable_candidates(cards_by_id, mapped)

    required = a.train_decks + a.adversaries
    if len(usable) < required:
        raise RuntimeError(
            f'structural screen needs {required} usable candidates, found {len(usable)}'
        )

    train_pool = usable[:a.train_decks]
    adversaries = usable[a.train_decks:required]

    policy_cls = POLICIES[a.policy]
    policy, training, training_complete = train_universal_policy(
        a, mapped, train_pool, policy_cls
    )

    proposals = []
    evaluations = {}
    duel_rows = []
    if training_complete:
        proposals = generate_structural_challengers(
            adversaries, legal_main, graph, a.challengers, a.mutation_seed
        )
        for index, spec in enumerate(proposals):
            deck = spec['deck']
            cid = hashlib.sha256('|'.join(deck).encode()).hexdigest()[:16]
            per_opp, aggregate, rows = evaluate_challenger(
                a, mapped, policy, cid, deck, adversaries
            )
            evaluations[cid] = {
                'proposal_index': index,
                'parent': spec['parent'],
                'method': spec['method'],
                'proposal_metadata': {
                    k: v for k, v in spec.items()
                    if k not in {'deck', 'parent', 'method'}
                },
                'main': dict(collections.Counter(deck)),
                'per_opponent': per_opp,
                'aggregate': aggregate,
            }
            duel_rows.extend(rows)

    certified = [
        cid for cid, row in evaluations.items()
        if row['aggregate']['certified']
    ]
    exploratory_best = None
    if certified:
        exploratory_best = max(
            certified,
            key=lambda cid: (
                evaluations[cid]['aggregate']['worst_opponent_win_wilson95_lower'],
                evaluations[cid]['aggregate']['mean_score_rate'],
                cid,
            ),
        )

    report = {
        'purpose': 'exploratory_structural_mutation_duel_screen',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'pilot_model': a.policy,
        'pilot_skill_certified_for_ranking': False,
        'deck_ranking_evidence': False,
        'training_complete': training_complete,
        'training_candidate_ids': [cid for cid, _ in train_pool],
        'adversary_candidate_ids': [cid for cid, _ in adversaries],
        'generated_challengers': len(proposals),
        'evaluated_challengers': len(evaluations),
        'seeds_per_opponent': a.seeds_per_opponent,
        'planned_duels': (
            len(proposals) * len(adversaries) * a.seeds_per_opponent * 2
        ),
        'completed_duels': sum(
            bool(row['result'].get('completed')) for row in duel_rows
        ),
        'exploratory_best_response_only': exploratory_best,
        'evaluations': evaluations,
        'duel_rows': duel_rows,
        'note': (
            'Structural proposals use only legal copy limits and unverified '
            'full-pool text-relation hypotheses. Actual paired-seat duel '
            'outcomes decide the exploratory screen. No final ranking is '
            'authorized until pilot competence is certified.'
        ),
    }
    dump(ROOT/'reports/structural_challenger_screen.json', report)
    print(json.dumps({
        'policy': a.policy,
        'training_complete': training_complete,
        'adversaries': len(adversaries),
        'challengers': len(proposals),
        'planned_duels': report['planned_duels'],
        'completed_duels': report['completed_duels'],
        'exploratory_best_response_only': exploratory_best,
        'deck_ranking_evidence': False,
    }))

    if not training_complete:
        raise SystemExit('structural challenger pilot training did not complete')
    if report['completed_duels'] != report['planned_duels']:
        raise SystemExit('structural challenger screen did not complete all planned duels')


if __name__ == '__main__':
    main()

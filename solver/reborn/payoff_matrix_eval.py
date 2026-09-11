"""Paired-seat head-to-head payoff matrix for frozen zero-prior pilots.

This module is duel-testing infrastructure. It does not by itself certify the
pilot as strong enough for final deck ranking. A single frozen policy controls
both seats from the same information-safe observation interface. Every matchup
is evaluated in both seat orientations on the same seeds.

No tournament lists, archetype labels, human card values, or historical/meta
priors enter the evaluator.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json

from .announce import enumerate_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .learn_probe import run_training_game
from .learning import SparsePolicy
from .learning_pilot import LearningPilot
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision
from .scalar_context_ab_eval import ScalarContextPolicy
from .search import validate

MSG_WIN = 5


POLICIES = {
    'canonical': SparsePolicy,
    'scalar_context': ScalarContextPolicy,
}


def usable_candidates(cards, mapped):
    rows = json.loads((ROOT/'data/processed/candidates-20260906.json').read_text())['candidates']
    usable = []
    for candidate in rows:
        deck = [cid for cid, n in candidate['main'].items() for _ in range(n)]
        if any(cid not in mapped for cid in deck):
            continue
        validate(deck, cards)
        usable.append((candidate['id'], deck))
    return usable


def train_universal_policy(a, mapped, train_pool, policy_cls):
    policy = policy_cls(seed=a.policy_seed, temperature=1.0, learning_rate=0.05)
    rows = []
    for game in range(a.train_games):
        left = game % len(train_pool)
        right = (left + 1 + (game // len(train_pool))) % len(train_pool)
        if left == right:
            right = (right + 1) % len(train_pool)
        seat0 = train_pool[left]
        seat1 = train_pool[right]
        if game % 2:
            seat0, seat1 = seat1, seat0
        seed = a.train_seed + game
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
    return policy, rows, complete


def _frozen_copy(policy, seed):
    return policy.__class__(
        seed=seed,
        temperature=policy.temperature,
        learning_rate=0.0,
        weights=dict(policy.weights),
    )


def run_frozen_policy_duel(
    library, database, scripts, decks, mapped, frozen_policy, seed, budget=5000
):
    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    policies = [_frozen_copy(frozen_policy, seed * 1009 + seat) for seat in (0, 1)]
    pilots = [
        LearningPilot(policies[seat], seed=seed * 101 + 17 + seat)
        for seat in (0, 1)
    ]
    before = [dict(policy.weights) for policy in policies]
    tracker = PublicTracker()
    decision_types = Counter()
    row = {
        'seed': seed,
        'status': 'pending',
        'steps': 0,
        'decisions': 0,
        'observation_checks': 0,
        'policy_view_checks': 0,
        'fallback_decisions': 0,
        'fallback_kinds': {},
        'blocker': None,
    }

    try:
        with Duel(library, database, scripts, seed=seed) as duel:
            for player, deck in enumerate(decks):
                for index, cid in enumerate(deck):
                    duel.add(mapped[cid]['passcode'], player, sequence=index)
            duel.start()

            for step in range(budget):
                status, messages = duel.process()
                tracker.consume(messages)
                row['steps'] = step + 1
                wins = [m for m in messages if m and m[0] == MSG_WIN]
                if wins:
                    winner = wins[0][1] if len(wins[0]) >= 2 and wins[0][1] in (0, 1) else None
                    row.update(
                        status='completed',
                        completed=True,
                        winner=winner,
                        decision_types=dict(sorted(decision_types.items())),
                        fallback_decisions=sum(p.fallback_decisions for p in pilots),
                        fallback_kinds=dict(sorted(
                            Counter(
                                {
                                    k: sum(p.fallback_kinds.get(k, 0) for p in pilots)
                                    for k in set().union(*(p.fallback_kinds for p in pilots))
                                }
                            ).items()
                        )),
                    )
                    break

                decision = extract_decision(messages)
                if decision is not None:
                    row['decisions'] += 1
                    decision_types[decision.kind] += 1
                    observation = observation_for(duel, decision.player, tracker)
                    row['observation_checks'] += 1
                    prompt = policy_prompt_view(decision, observation)
                    assert_no_hidden_code_leak(prompt, observation)
                    row['policy_view_checks'] += 1
                    pilot = pilots[decision.player]
                    if decision.kind == 'announce_card':
                        legal_codes = enumerate_declarable(
                            database, decision.meta['opcodes'], allowed_codes
                        )
                        response = pilot.choose_announce_card(
                            decision, prompt, observation, legal_codes
                        )
                    else:
                        response = pilot.choose(decision, prompt, observation)
                    duel.respond(response)
                    continue

                if status != 2:
                    raise UnsupportedInteraction(
                        f'engine stopped without win/decision: status={status}, '
                        f'messages={[m[0] for m in messages if m]}'
                    )
            else:
                raise UnsupportedInteraction(
                    f'payoff duel exceeded {budget} engine steps'
                )
    except Exception as exc:
        row.update(
            status='blocked',
            completed=False,
            blocker=f'{type(exc).__name__}: {exc}',
            decision_types=dict(sorted(decision_types.items())),
            fallback_decisions=sum(p.fallback_decisions for p in pilots),
        )
        return row

    if any(policy.weights != start for policy, start in zip(policies, before)):
        row.update(
            status='blocked',
            completed=False,
            blocker='UnsupportedInteraction: frozen payoff policy mutated',
        )
    elif row.get('status') != 'completed':
        row.update(
            status='blocked',
            completed=False,
            blocker='UnsupportedInteraction: payoff duel did not complete',
        )
    elif row['observation_checks'] != row['decisions'] or row['policy_view_checks'] != row['decisions']:
        row.update(
            status='blocked',
            completed=False,
            blocker='UnsupportedInteraction: not every payoff decision passed privacy checks',
        )
    return row


def matchup_schedule(population, seeds):
    """Return deterministic unordered matchups including the diagonal.

    Every scheduled row is later played twice: A-first and A-second.
    """
    out = []
    for i, (aid, adeck) in enumerate(population):
        for j in range(i, len(population)):
            bid, bdeck = population[j]
            for seed in seeds:
                out.append({
                    'a': aid,
                    'b': bid,
                    'seed': seed,
                    'a_deck': adeck,
                    'b_deck': bdeck,
                })
    return out


def _empty_sample():
    return {
        'wins': 0,
        'losses': 0,
        'draws': 0,
        'games': 0,
        'unsupported': 0,
        'timeouts': 0,
        'fallback_decisions': 0,
        'certified': True,
    }


def _record(sample, result, seat_for_deck):
    sample['games'] += 1
    if not result.get('completed'):
        sample['unsupported'] += 1
        sample['certified'] = False
        if result.get('blocker') and 'exceeded' in result['blocker']:
            sample['timeouts'] += 1
        return
    sample['fallback_decisions'] += int(result.get('fallback_decisions', 0))
    if result.get('fallback_decisions', 0):
        sample['certified'] = False
    winner = result.get('winner')
    if winner not in (0, 1):
        sample['draws'] += 1
    elif winner == seat_for_deck:
        sample['wins'] += 1
    else:
        sample['losses'] += 1


def build_matrix(population, rows):
    ids = [cid for cid, _ in population]
    matrix = {
        deck: {
            opp: {'first': _empty_sample(), 'second': _empty_sample()}
            for opp in ids
        }
        for deck in ids
    }
    for row in rows:
        a = row['a']
        b = row['b']
        first = row['a_first_result']
        second = row['a_second_result']

        _record(matrix[a][b]['first'], first, 0)
        _record(matrix[b][a]['second'], first, 1)

        _record(matrix[a][b]['second'], second, 1)
        _record(matrix[b][a]['first'], second, 0)

    for deck in ids:
        for opp in ids:
            for seat in ('first', 'second'):
                sample = matrix[deck][opp][seat]
                sample['certified'] = bool(
                    sample['certified']
                    and sample['games'] > 0
                    and sample['unsupported'] == 0
                    and sample['timeouts'] == 0
                    and sample['fallback_decisions'] == 0
                )
    return matrix


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--policy', choices=sorted(POLICIES), default='canonical')
    p.add_argument('--train-games', type=int, default=128)
    p.add_argument('--train-decks', type=int, default=12)
    p.add_argument('--population-size', type=int, default=6)
    p.add_argument('--seeds-per-matchup', type=int, default=4)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=191000)
    p.add_argument('--eval-seed', type=int, default=201000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(
        a.train_games, a.train_decks, a.population_size, a.seeds_per_matchup
    ) < 1:
        raise ValueError('payoff matrix sizes must all be positive')
    if a.train_decks < 2:
        raise ValueError('payoff matrix training requires at least two decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = usable_candidates(cards, mapped)
    required = a.train_decks + a.population_size
    if len(usable) < required:
        raise RuntimeError(
            f'payoff matrix needs {required} usable candidates, found {len(usable)}'
        )

    train_pool = usable[:a.train_decks]
    population = usable[a.train_decks:required]
    policy_cls = POLICIES[a.policy]
    policy, training, training_complete = train_universal_policy(
        a, mapped, train_pool, policy_cls
    )
    policy_path = ROOT/'reports/payoff_policy.json'
    policy.save(policy_path)

    results = []
    if training_complete:
        seeds = [a.eval_seed + i for i in range(a.seeds_per_matchup)]
        for item in matchup_schedule(population, seeds):
            base = {
                'a': item['a'],
                'b': item['b'],
                'seed': item['seed'],
            }
            first = run_frozen_policy_duel(
                a.library, a.database, a.scripts,
                (item['a_deck'], item['b_deck']),
                mapped, policy, item['seed'], a.budget,
            )
            second = run_frozen_policy_duel(
                a.library, a.database, a.scripts,
                (item['b_deck'], item['a_deck']),
                mapped, policy, item['seed'], a.budget,
            )
            results.append({
                **base,
                'a_first_result': first,
                'a_second_result': second,
            })

    matrix = build_matrix(population, results) if results else {}
    all_samples_certified = bool(matrix) and all(
        sample['certified']
        for row in matrix.values()
        for seats in row.values()
        for sample in seats.values()
    )
    report = {
        'purpose': 'paired_seat_deck_payoff_matrix_infrastructure',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'pilot_model': a.policy,
        'pilot_skill_certified_for_ranking': False,
        'deck_ranking_evidence': False,
        'training_complete': training_complete,
        'training_candidate_ids': [cid for cid, _ in train_pool],
        'population_candidate_ids': [cid for cid, _ in population],
        'training_games': len(training),
        'training_completed': sum(bool(r.get('completed')) for r in training),
        'seeds_per_matchup': a.seeds_per_matchup,
        'scheduled_unordered_matchups_including_diagonal': (
            a.population_size * (a.population_size + 1) // 2
        ),
        'planned_duels': (
            a.population_size * (a.population_size + 1) // 2
            * a.seeds_per_matchup * 2
        ),
        'completed_duels': sum(
            bool(r[side].get('completed'))
            for r in results
            for side in ('a_first_result', 'a_second_result')
        ),
        'all_samples_certified': all_samples_certified,
        'policy_file': 'reports/payoff_policy.json',
        'matrix': matrix,
        'results': results,
        'note': (
            'This produces actual paired-seat head-to-head duel samples. The '
            'report intentionally refuses to call them final deck-ranking '
            'evidence until a separate pilot-skill gate has been promoted.'
        ),
    }
    dump(ROOT/'reports/payoff_matrix.json', report)
    print(json.dumps({
        'policy': a.policy,
        'training_complete': training_complete,
        'population': len(population),
        'planned_duels': report['planned_duels'],
        'completed_duels': report['completed_duels'],
        'all_samples_certified': all_samples_certified,
        'deck_ranking_evidence': False,
    }))

    if not training_complete:
        raise SystemExit('payoff matrix pilot training did not complete')
    if report['completed_duels'] != report['planned_duels']:
        raise SystemExit('payoff matrix did not complete all planned duels')


if __name__ == '__main__':
    main()

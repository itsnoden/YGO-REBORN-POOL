"""Direct frozen-policy head-to-head duel evaluation.

Both policies act only through the filtered information-safe observation/prompt
boundary.  The exact policy subclass and weights are preserved for each seat.
No learning occurs during evaluation.

This is pilot-skill infrastructure.  When used on mirror decks with paired seat
swaps it compares two pilots directly without allowing deck quality or a common
third-party baseline to masquerade as policy strength.
"""
from __future__ import annotations

from collections import Counter

from .announce import enumerate_declarable
from .effects import UnsupportedInteraction
from .learning_pilot import LearningPilot
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .pilot_eval import frozen_policy_copy
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision

MSG_WIN = 5


def run_policy_match(
    library, database, scripts, deck, mapped,
    policy_a, policy_b, a_seat, seed, budget=5000,
):
    if a_seat not in (0, 1):
        raise ValueError('a_seat must be 0 or 1')

    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    seat_policy = {
        a_seat: frozen_policy_copy(policy_a, seed * 1009 + a_seat),
        1 - a_seat: frozen_policy_copy(policy_b, seed * 1013 + (1 - a_seat)),
    }
    pilots = {
        seat: LearningPilot(seat_policy[seat], seed=seed * 101 + 17 + seat)
        for seat in (0, 1)
    }
    before = {seat: dict(seat_policy[seat].weights) for seat in (0, 1)}
    tracker = PublicTracker()
    decision_types = Counter()
    row = {
        'seed': seed,
        'a_seat': a_seat,
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
            for player in (0, 1):
                for index, cid in enumerate(deck):
                    duel.add(mapped[cid]['passcode'], player, sequence=index)
            duel.start()

            for step in range(budget):
                status, messages = duel.process()
                tracker.consume(messages)
                row['steps'] = step + 1

                wins = [m for m in messages if m and m[0] == MSG_WIN]
                if wins:
                    winner = (
                        wins[0][1]
                        if len(wins[0]) >= 2 and wins[0][1] in (0, 1)
                        else None
                    )
                    fallback = Counter()
                    for pilot in pilots.values():
                        fallback.update(pilot.fallback_kinds)
                    row.update(
                        status='completed',
                        completed=True,
                        winner_seat_debug_only=winner,
                        a_result=(
                            'win' if winner == a_seat
                            else 'loss' if winner == 1 - a_seat
                            else 'draw'
                        ),
                        fallback_decisions=sum(
                            p.fallback_decisions for p in pilots.values()
                        ),
                        fallback_kinds=dict(sorted(fallback.items())),
                        decision_types=dict(sorted(decision_types.items())),
                    )
                    break

                decision = extract_decision(messages)
                if decision is not None:
                    row['decisions'] += 1
                    decision_types[decision.kind] += 1
                    observation = observation_for(
                        duel, decision.player, tracker
                    )
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
                        response = pilot.choose(
                            decision, prompt, observation
                        )
                    duel.respond(response)
                    continue

                if status != 2:
                    raise UnsupportedInteraction(
                        f'policy match stopped without win/decision: '
                        f'status={status}, messages={[m[0] for m in messages if m]}'
                    )
            else:
                raise UnsupportedInteraction(
                    f'policy match exceeded {budget} engine steps'
                )
    except Exception as exc:
        row.update(
            status='blocked',
            completed=False,
            blocker=f'{type(exc).__name__}: {exc}',
            fallback_decisions=sum(
                p.fallback_decisions for p in pilots.values()
            ),
            decision_types=dict(sorted(decision_types.items())),
        )
        return row

    if any(
        seat_policy[seat].weights != before[seat]
        for seat in (0, 1)
    ):
        row.update(
            status='blocked',
            completed=False,
            blocker='UnsupportedInteraction: frozen policy mutated',
        )
    elif row.get('status') != 'completed':
        row.update(
            status='blocked',
            completed=False,
            blocker='UnsupportedInteraction: direct policy duel did not complete',
        )
    elif (
        row['observation_checks'] != row['decisions']
        or row['policy_view_checks'] != row['decisions']
    ):
        row.update(
            status='blocked',
            completed=False,
            blocker='UnsupportedInteraction: privacy check count mismatch',
        )
    return row


def evaluate_policy_pair(
    library, database, scripts, eval_pool, mapped,
    policy_a, policy_b, pairs_per_deck, seed_base, budget=5000,
):
    rows = []
    for deck_index, (candidate_id, deck) in enumerate(eval_pool):
        for pair in range(pairs_per_deck):
            seed = seed_base + deck_index * 100 + pair
            for a_seat in (0, 1):
                row = {
                    'candidate': candidate_id,
                    'pair': pair,
                    'seed': seed,
                    'a_seat': a_seat,
                }
                row.update(run_policy_match(
                    library, database, scripts, deck, mapped,
                    policy_a, policy_b, a_seat, seed, budget,
                ))
                rows.append(row)

    completed = sum(bool(r.get('completed')) for r in rows)
    wins = sum(r.get('a_result') == 'win' for r in rows)
    losses = sum(r.get('a_result') == 'loss' for r in rows)
    draws = sum(r.get('a_result') == 'draw' for r in rows)
    return {
        'games': len(rows),
        'completed': completed,
        'a_wins': wins,
        'a_losses': losses,
        'draws': draws,
        'a_score_rate': (
            (wins + 0.5 * draws) / completed if completed else None
        ),
        'fallback_decisions': sum(
            r.get('fallback_decisions', 0) for r in rows
        ),
        'all_completed': completed == len(rows),
        'rows': rows,
    }

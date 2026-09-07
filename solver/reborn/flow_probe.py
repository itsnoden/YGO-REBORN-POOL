"""Drive generated decks through the real engine until a win or a strict blocker.

This is a correctness/protocol coverage probe, NOT a strength evaluator.  The
baseline policy is intentionally conservative and deterministic.  Results from
this module must never be interpreted as deck win rates or search priors.
"""
import argparse
import json
import struct

from .announce import choose_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision, conservative_response
from .search import validate

MSG_WIN = 5


def _assert_filtered_observation(observation):
    """Fail closed if an anonymous opponent zone accidentally exposes a code."""
    viewer = observation['viewer']
    for player, row in enumerate(observation['players']):
        if player == viewer:
            continue
        for card in row['hand']:
            if card.get('hidden') and 'code' in card:
                raise UnsupportedInteraction('opponent hidden hand code leaked')
        for card in row['extra']:
            if card.get('hidden') and 'code' in card:
                raise UnsupportedInteraction('opponent hidden Extra Deck code leaked')
    return True


def run_one(library, database, scripts, deck0, deck1, mapped, seed, budget=5000):
    row = dict(seed=seed, status='pending', steps=0, decisions=0,
               observation_checks=0, policy_view_checks=0, message_types=[], blocker=None)
    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    tracker = PublicTracker()
    with Duel(library, database, scripts, seed=seed) as duel:
        for player, deck in enumerate((deck0, deck1)):
            for index, cid in enumerate(deck):
                duel.add(mapped[cid]['passcode'], player, sequence=index)
        duel.start()
        for step in range(budget):
            status, messages = duel.process()
            tracker.consume(messages)
            row['steps'] = step + 1
            row['message_types'].extend(m[0] for m in messages if m)
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                row.update(status='completed', completed=True)
                return row
            decision = extract_decision(messages)
            if decision is not None:
                row['decisions'] += 1

                # Build the same information-safe state/prompt objects a future
                # learned pilot will consume. Neither object affects this
                # conservative baseline's action choice.
                observation = observation_for(duel, decision.player, tracker)
                _assert_filtered_observation(observation)
                row['observation_checks'] += 1
                policy_view = policy_prompt_view(decision, observation)
                assert_no_hidden_code_leak(policy_view, observation)
                row['policy_view_checks'] += 1

                if decision.kind == 'announce_card':
                    code = choose_declarable(database, decision.meta['opcodes'], allowed_codes)
                    response = struct.pack('<i', code)
                else:
                    response = conservative_response(decision)
                duel.respond(response)
                continue
            if status != 2:
                raise UnsupportedInteraction(
                    f'engine stopped without win/decision: status={status}, messages={[m[0] for m in messages if m]}'
                )
        raise UnsupportedInteraction(f'flow probe exceeded {budget} engine steps')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--count', type=int, default=8)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--seed', type=int, default=3000)
    a = p.parse_args()

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    candidates = json.loads((ROOT/'data/processed/candidates-20260906.json').read_text())['candidates']
    usable = []
    for c in candidates:
        deck = [cid for cid, n in c['main'].items() for _ in range(n)]
        if any(cid not in mapped for cid in deck):
            continue
        validate(deck, cards)
        usable.append((c['id'], deck))
        if len(usable) >= a.count:
            break

    results = []
    for i, (cid, deck) in enumerate(usable):
        opponent_id, opponent = usable[(i + 1) % len(usable)]
        row = dict(candidate=cid, opponent=opponent_id, seed=a.seed+i)
        try:
            row.update(run_one(a.library, a.database, a.scripts, deck, opponent, mapped,
                               a.seed+i, a.budget))
        except Exception as exc:
            row.update(status='blocked', completed=False,
                       blocker=f'{type(exc).__name__}: {exc}')
        results.append(row)

    report = {
        'purpose': 'protocol_observation_prompt_filter_and_complete_duel_correctness_only',
        'strength_evidence': False,
        'profile': 'experimental_current_tcg_not_reborn_confirmed',
        'baseline_policy': 'deterministic_conservative_legal_actions',
        'attempted': len(results),
        'completed': sum(bool(r.get('completed')) for r in results),
        'observation_checks': sum(r.get('observation_checks', 0) for r in results),
        'policy_view_checks': sum(r.get('policy_view_checks', 0) for r in results),
        'results': results,
        'note': 'Do not use these outcomes as deck rankings, win rates, or search priors.',
    }
    dump(ROOT/'reports/flow_probe.json', report)
    print(json.dumps({k: report[k] for k in ('attempted', 'completed', 'observation_checks', 'policy_view_checks')}))


if __name__ == '__main__':
    main()

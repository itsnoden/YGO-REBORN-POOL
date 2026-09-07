"""Paired-seat stochastic piloting for adversarial engine-coverage testing.

This deliberately weak pilot has no card-specific preferences. It randomizes
among legal engine actions from information-safe observations/prompts to force
deeper and more varied interactions than the conservative flow probe. Outcomes
are NOT deck strength evidence and must never feed candidate selection/oracle.
"""
import argparse
from collections import Counter
import json
import struct

from .announce import choose_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .pilot import StochasticLegalPilot
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision
from .search import validate

MSG_WIN = 5


def run_game(library, database, scripts, decks, mapped, seed, budget=5000):
    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    pilots = (StochasticLegalPilot(seed * 2 + 1), StochasticLegalPilot(seed * 2 + 2))
    tracker = PublicTracker()
    row = {
        'seed': seed, 'status': 'pending', 'steps': 0, 'decisions': 0,
        'observation_checks': 0, 'policy_view_checks': 0,
        'decision_types': {}, 'message_types': {}, 'blocker': None,
    }
    decision_types = Counter(); message_types = Counter()
    with Duel(library, database, scripts, seed=seed) as duel:
        for player, deck in enumerate(decks):
            for index, cid in enumerate(deck):
                duel.add(mapped[cid]['passcode'], player, sequence=index)
        duel.start()
        for step in range(budget):
            status, messages = duel.process(); tracker.consume(messages)
            row['steps'] = step + 1
            message_types.update(m[0] for m in messages if m)
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                row.update(status='completed', completed=True)
                if len(wins[0]) >= 2:
                    row['winner_seat_debug_only'] = wins[0][1]
                break
            decision = extract_decision(messages)
            if decision is not None:
                row['decisions'] += 1; decision_types[decision.kind] += 1
                observation = observation_for(duel, decision.player, tracker)
                row['observation_checks'] += 1
                prompt = policy_prompt_view(decision, observation)
                assert_no_hidden_code_leak(prompt, observation)
                row['policy_view_checks'] += 1
                if decision.kind == 'announce_card':
                    code = choose_declarable(database, decision.meta['opcodes'], allowed_codes)
                    response = struct.pack('<i', code)
                else:
                    # StochasticLegalPilot consumes the information-safe state
                    # observation. The filtered prompt is audited separately above
                    # for future learning policies and must not replace observation.
                    response = pilots[decision.player].choose(decision, observation)
                duel.respond(response)
                continue
            if status != 2:
                raise UnsupportedInteraction(
                    f'engine stopped without win/decision: status={status}, messages={[m[0] for m in messages if m]}'
                )
        else:
            raise UnsupportedInteraction(f'pilot probe exceeded {budget} engine steps')
    row['decision_types'] = dict(sorted(decision_types.items()))
    row['message_types'] = {str(k): v for k, v in sorted(message_types.items())}
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True); p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True); p.add_argument('--pairs', type=int, default=4)
    p.add_argument('--budget', type=int, default=5000); p.add_argument('--seed', type=int, default=5000)
    a = p.parse_args()

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    candidates = json.loads((ROOT/'data/processed/candidates-20260906.json').read_text())['candidates']
    usable = []
    for c in candidates:
        deck = [cid for cid, n in c['main'].items() for _ in range(n)]
        if any(cid not in mapped for cid in deck): continue
        validate(deck, cards); usable.append((c['id'], deck))
        if len(usable) >= a.pairs + 1: break
    if len(usable) < 2:
        raise RuntimeError('need at least two mapped candidates')

    results = []
    for pair in range(min(a.pairs, len(usable) - 1)):
        aid, adeck = usable[pair]; bid, bdeck = usable[pair + 1]
        for swap in (False, True):
            seat0 = (bid, bdeck) if swap else (aid, adeck)
            seat1 = (aid, adeck) if swap else (bid, bdeck)
            seed = a.seed + pair * 2 + int(swap)
            meta = {'pair': pair, 'seat0': seat0[0], 'seat1': seat1[0], 'seed': seed}
            try:
                meta.update(run_game(a.library, a.database, a.scripts,
                                     (seat0[1], seat1[1]), mapped, seed, a.budget))
            except Exception as exc:
                meta.update(status='blocked', completed=False,
                            blocker=f'{type(exc).__name__}: {exc}')
            results.append(meta)

    all_decisions = Counter(); all_messages = Counter()
    for row in results:
        all_decisions.update(row.get('decision_types', {}))
        all_messages.update({int(k): v for k, v in row.get('message_types', {}).items()})
    completed = sum(bool(r.get('completed')) for r in results)
    report = {
        'purpose': 'stochastic_legal_pilot_adversarial_coverage_only',
        'strength_evidence': False,
        'search_prior': False,
        'profile': 'reborn',
        'pilot': 'seeded_stochastic_legal_no_card_specific_preferences',
        'paired_seats': True,
        'attempted': len(results),
        'completed': completed,
        'observation_checks': sum(r.get('observation_checks', 0) for r in results),
        'policy_view_checks': sum(r.get('policy_view_checks', 0) for r in results),
        'decision_types': dict(sorted(all_decisions.items())),
        'message_types': {str(k): v for k, v in sorted(all_messages.items())},
        'results': results,
        'note': 'Winner fields are debug-only. Do not convert these games into deck win rates or fitness.',
    }
    dump(ROOT/'reports/pilot_probe.json', report)
    print(json.dumps({k: report[k] for k in ('attempted','completed','observation_checks','policy_view_checks','decision_types')}))
    if completed != len(results):
        raise SystemExit(f'stochastic pilot coverage failed: completed {completed}/{len(results)} games')


if __name__ == '__main__':
    main()

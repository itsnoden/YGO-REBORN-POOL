"""Drive generated decks through the real engine until a win or a strict blocker.

This is a correctness/protocol coverage probe, NOT a strength evaluator.  The
baseline policy is intentionally conservative and deterministic.  Results from
this module must never be interpreted as deck win rates or search priors.
"""
import argparse
import json

from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .ocgcore import Duel
from .protocol import extract_decision, conservative_response
from .search import validate

MSG_WIN = 5


def run_one(library, database, scripts, deck0, deck1, mapped, seed, budget=5000):
    row = dict(seed=seed, status='pending', steps=0, decisions=0, message_types=[], blocker=None)
    with Duel(library, database, scripts, seed=seed) as duel:
        for player, deck in enumerate((deck0, deck1)):
            for index, cid in enumerate(deck):
                duel.add(mapped[cid]['passcode'], player, sequence=index)
        duel.start()
        for step in range(budget):
            status, messages = duel.process()
            row['steps'] = step + 1
            row['message_types'].extend(m[0] for m in messages if m)
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                # MSG_WIN payload begins winner/reason, but do not need it for
                # protocol coverage certification.
                row.update(status='completed', completed=True)
                return row
            decision = extract_decision(messages)
            if decision is not None:
                row['decisions'] += 1
                # Explicitly materialize only the acting player's filtered view.
                # This assertion prevents future policies from consuming raw prompts.
                decision.view_for(decision.player)
                duel.respond(conservative_response(decision))
                continue
            # status 2 means engine can continue internally.  Any other state
            # without a decision or win is a strict coverage blocker.
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
        'purpose': 'protocol_and_complete_duel_correctness_only',
        'strength_evidence': False,
        'profile': 'experimental_current_tcg_not_reborn_confirmed',
        'baseline_policy': 'deterministic_conservative_legal_actions',
        'attempted': len(results),
        'completed': sum(bool(r.get('completed')) for r in results),
        'results': results,
        'note': 'Do not use these outcomes as deck rankings, win rates, or search priors.',
    }
    dump(ROOT/'reports/flow_probe.json', report)
    print(json.dumps({k: report[k] for k in ('attempted', 'completed')}))


if __name__ == '__main__':
    main()

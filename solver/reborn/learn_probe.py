"""Train the from-scratch pilot on complete YGO Reborn engine self-play.

This is a pilot-training correctness smoke test under the user-confirmed Reborn
rules profile. It proves learning data can flow from safe observations to duel
outcomes; it does NOT establish deck strength, pilot optimality, or a #1 deck.
"""
import argparse
from collections import Counter
import json
import struct

from .announce import choose_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .learning_pilot import LearningPilot
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision
from .search import validate

MSG_WIN = 5


def run_training_game(library, database, scripts, decks, mapped, policy, seed, budget=5000):
    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    pilot = LearningPilot(policy, seed=seed * 17 + 3)
    tracker = PublicTracker(); decision_types = Counter()
    row = {'seed': seed, 'status': 'pending', 'steps': 0, 'decisions': 0,
           'learned_decisions': 0, 'complex_learned_decisions': 0,
           'fallback_decisions': 0, 'fallback_kinds': {}, 'blocker': None}
    with Duel(library, database, scripts, seed=seed) as duel:
        for player, deck in enumerate(decks):
            for index, cid in enumerate(deck):
                duel.add(mapped[cid]['passcode'], player, sequence=index)
        duel.start()
        for step in range(budget):
            status, messages = duel.process(); tracker.consume(messages)
            row['steps'] = step + 1
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                winner = wins[0][1] if len(wins[0]) >= 2 and wins[0][1] in (0, 1) else None
                pilot.finish(winner)
                row.update(status='completed', completed=True,
                           winner_seat_debug_only=winner,
                           learned_decisions=pilot.learned_decisions,
                           complex_learned_decisions=pilot.complex_learned_decisions,
                           fallback_decisions=pilot.fallback_decisions,
                           fallback_kinds=dict(sorted(pilot.fallback_kinds.items())),
                           decision_types=dict(sorted(decision_types.items())))
                return row
            decision = extract_decision(messages)
            if decision is not None:
                row['decisions'] += 1; decision_types[decision.kind] += 1
                observation = observation_for(duel, decision.player, tracker)
                prompt = policy_prompt_view(decision, observation)
                assert_no_hidden_code_leak(prompt, observation)
                if decision.kind == 'announce_card':
                    code = choose_declarable(database, decision.meta['opcodes'], allowed_codes)
                    response = struct.pack('<i', code)
                    pilot.fallback_decisions += 1
                    pilot.fallback_kinds['announce_card'] += 1
                else:
                    response = pilot.choose(decision, prompt, observation)
                duel.respond(response); continue
            if status != 2:
                raise UnsupportedInteraction(
                    f'engine stopped without win/decision: status={status}, messages={[m[0] for m in messages if m]}'
                )
        raise UnsupportedInteraction(f'learning probe exceeded {budget} engine steps')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True); p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True); p.add_argument('--games', type=int, default=8)
    p.add_argument('--budget', type=int, default=5000); p.add_argument('--seed', type=int, default=7000)
    p.add_argument('--policy-seed', type=int, default=20260906)
    a = p.parse_args()

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    candidates = json.loads((ROOT/'data/processed/candidates-20260906.json').read_text())['candidates']
    usable = []
    for candidate in candidates:
        deck = [cid for cid, n in candidate['main'].items() for _ in range(n)]
        if any(cid not in mapped for cid in deck): continue
        validate(deck, cards); usable.append((candidate['id'], deck))
        if len(usable) >= 8: break
    if len(usable) < 2: raise RuntimeError('need at least two usable candidates')

    policy = SparsePolicy(seed=a.policy_seed, temperature=1.0, learning_rate=0.05)
    results = []
    for game in range(a.games):
        left = game % (len(usable) - 1); right = left + 1
        swap = bool(game % 2)
        seat0 = usable[right] if swap else usable[left]
        seat1 = usable[left] if swap else usable[right]
        row = {'game': game, 'seat0': seat0[0], 'seat1': seat1[0], 'seed': a.seed + game}
        try:
            row.update(run_training_game(a.library, a.database, a.scripts,
                                         (seat0[1], seat1[1]), mapped, policy,
                                         a.seed + game, a.budget))
        except Exception as exc:
            row.update(status='blocked', completed=False,
                       blocker=f'{type(exc).__name__}: {exc}')
        results.append(row)

    policy_path = ROOT/'reports/learned_policy_reborn_smoke.json'
    policy.save(policy_path)
    decision_types = Counter(); fallback_kinds = Counter()
    for row in results:
        decision_types.update(row.get('decision_types', {}))
        fallback_kinds.update(row.get('fallback_kinds', {}))
    completed = sum(bool(r.get('completed')) for r in results)
    report = {
        'purpose': 'from_scratch_policy_training_smoke_only',
        'strength_evidence': False,
        'deck_ranking_evidence': False,
        'profile': 'reborn',
        'external_strategy_priors': False,
        'policy': 'sparse_softmax_reinforce_v2_complex_actions',
        'attempted': len(results),
        'completed': completed,
        'learned_decisions': sum(r.get('learned_decisions', 0) for r in results),
        'complex_learned_decisions': sum(r.get('complex_learned_decisions', 0) for r in results),
        'fallback_decisions': sum(r.get('fallback_decisions', 0) for r in results),
        'fallback_kinds': dict(sorted(fallback_kinds.items())),
        'weight_count': len(policy.weights),
        'decision_types': dict(sorted(decision_types.items())),
        'policy_file': 'reports/learned_policy_reborn_smoke.json',
        'results': results,
        'note': 'Training outcomes update pilot weights only. Do not use these smoke games to rank decks.',
    }
    dump(ROOT/'reports/learn_probe.json', report)
    print(json.dumps({k: report[k] for k in ('attempted','completed','learned_decisions','complex_learned_decisions','fallback_decisions','fallback_kinds','weight_count')}))
    if completed != len(results):
        raise SystemExit(f'learning smoke failed: completed {completed}/{len(results)} games')
    if report['learned_decisions'] <= 0 or report['weight_count'] <= 0:
        raise SystemExit('learning smoke completed games but produced no learned policy updates')


if __name__ == '__main__':
    main()

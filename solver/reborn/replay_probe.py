"""Verify deterministic response-history replay for counterfactual training.

This is infrastructure only.  It does not rank decks and it does not expose
referee-hidden information to a policy.  A source duel is played from filtered
observations, then a fresh duel with the same deck and core seed is required to
reproduce the same decision prompts and winner when fed the exact recorded
responses.

Reliable replay is the prerequisite for later *offline* counterfactual action
training.  Counterfactual outcomes must never be used as a live policy input,
because a rollout from one realized hidden state could otherwise leak future
hidden information indirectly.
"""
from __future__ import annotations

import argparse
import json
import struct

from .announce import choose_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .pilot import StochasticLegalPilot
from .pilot_eval import _usable_candidates
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision
from .search import validate

MSG_WIN = 5


def _normal(value):
    if isinstance(value, bytes):
        return {'bytes_hex': value.hex()}
    if isinstance(value, dict):
        return {str(k): _normal(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normal(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _card(card):
    return None if card is None else _normal(card.public())


def _decision_fingerprint(decision):
    return {
        'kind': decision.kind,
        'player': decision.player,
        'minimum': decision.minimum,
        'maximum': decision.maximum,
        'cancelable': bool(decision.cancelable),
        'actions': [
            {
                'label': action.label,
                'response_hex': action.response.hex(),
                'card': _card(action.card),
                'description': action.description,
                'client_mode': action.client_mode,
                'extra': _normal(action.extra),
            }
            for action in decision.actions
        ],
        'cards': [_card(card) for card in decision.cards],
        'meta': _normal(decision.meta),
    }


def _safe_fingerprint(observation, prompt):
    return json.dumps(
        {'observation': _normal(observation), 'prompt': _normal(prompt)},
        sort_keys=True,
        separators=(',', ':'),
    )


def _load_deck():
    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    if not usable:
        raise RuntimeError('no mapped legal candidate available for replay probe')
    candidate_id, deck = usable[0]
    validate(deck, cards)
    return candidate_id, deck, mapped


def _start_duel(library, database, scripts, seed, deck, mapped):
    duel = Duel(library, database, scripts, seed=seed)
    for player in (0, 1):
        for index, cid in enumerate(deck):
            duel.add(mapped[cid]['passcode'], player, sequence=index)
    duel.start()
    return duel


def _record_game(library, database, scripts, seed, deck, mapped, budget):
    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    pilots = [StochasticLegalPilot(seed * 103 + 11), StochasticLegalPilot(seed * 103 + 29)]
    tracker = PublicTracker()
    history = []
    observation_checks = 0
    policy_view_checks = 0

    with _start_duel(library, database, scripts, seed, deck, mapped) as duel:
        for step in range(budget):
            status, messages = duel.process()
            tracker.consume(messages)
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                return {
                    'winner': wins[0][1] if len(wins[0]) >= 2 else None,
                    'steps': step + 1,
                    'history': history,
                    'observation_checks': observation_checks,
                    'policy_view_checks': policy_view_checks,
                }

            decision = extract_decision(messages)
            if decision is not None:
                observation = observation_for(duel, decision.player, tracker)
                observation_checks += 1
                prompt = policy_prompt_view(decision, observation)
                assert_no_hidden_code_leak(prompt, observation)
                policy_view_checks += 1
                if decision.kind == 'announce_card':
                    code = choose_declarable(database, decision.meta['opcodes'], allowed_codes)
                    response = struct.pack('<i', code)
                else:
                    response = pilots[decision.player].choose(decision, observation)
                history.append({
                    'decision': _decision_fingerprint(decision),
                    'safe_fingerprint': _safe_fingerprint(observation, prompt),
                    'response_hex': response.hex(),
                })
                duel.respond(response)
                continue

            if status != 2:
                raise UnsupportedInteraction(
                    f'recording stopped without win/decision: status={status}, '
                    f'messages={[m[0] for m in messages if m]}'
                )
    raise UnsupportedInteraction(f'recording exceeded {budget} engine steps')


def _replay_game(library, database, scripts, seed, deck, mapped, history, expected_winner, budget):
    tracker = PublicTracker()
    cursor = 0
    checks = 0
    with _start_duel(library, database, scripts, seed, deck, mapped) as duel:
        for step in range(budget):
            status, messages = duel.process()
            tracker.consume(messages)
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                winner = wins[0][1] if len(wins[0]) >= 2 else None
                if cursor != len(history):
                    raise UnsupportedInteraction(
                        f'replay ended after {cursor}/{len(history)} recorded decisions'
                    )
                if winner != expected_winner:
                    raise UnsupportedInteraction(
                        f'replay winner changed: recorded={expected_winner}, replay={winner}'
                    )
                return {'winner': winner, 'steps': step + 1, 'decisions_verified': checks}

            decision = extract_decision(messages)
            if decision is not None:
                if cursor >= len(history):
                    raise UnsupportedInteraction('replay produced an extra decision')
                expected = history[cursor]
                actual_decision = _decision_fingerprint(decision)
                if actual_decision != expected['decision']:
                    raise UnsupportedInteraction(
                        f'decision mismatch at replay index {cursor}: '
                        f'{decision.kind}/P{decision.player}'
                    )
                observation = observation_for(duel, decision.player, tracker)
                prompt = policy_prompt_view(decision, observation)
                assert_no_hidden_code_leak(prompt, observation)
                if _safe_fingerprint(observation, prompt) != expected['safe_fingerprint']:
                    raise UnsupportedInteraction(
                        f'information-set mismatch at replay index {cursor}: '
                        f'{decision.kind}/P{decision.player}'
                    )
                duel.respond(bytes.fromhex(expected['response_hex']))
                cursor += 1
                checks += 1
                continue

            if status != 2:
                raise UnsupportedInteraction(
                    f'replay stopped without win/decision: status={status}, '
                    f'messages={[m[0] for m in messages if m]}'
                )
    raise UnsupportedInteraction(f'replay exceeded {budget} engine steps')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--count', type=int, default=2)
    p.add_argument('--seed', type=int, default=52000)
    p.add_argument('--budget', type=int, default=5000)
    a = p.parse_args()
    if a.count < 1:
        raise ValueError('count must be positive')

    candidate_id, deck, mapped = _load_deck()
    rows = []
    for offset in range(a.count):
        seed = a.seed + offset
        row = {'seed': seed, 'status': 'pending'}
        try:
            recorded = _record_game(a.library, a.database, a.scripts, seed, deck, mapped, a.budget)
            replayed = _replay_game(
                a.library, a.database, a.scripts, seed, deck, mapped,
                recorded['history'], recorded['winner'], a.budget,
            )
            row.update(
                status='completed',
                completed=True,
                winner=recorded['winner'],
                recorded_steps=recorded['steps'],
                replay_steps=replayed['steps'],
                decisions=len(recorded['history']),
                decisions_verified=replayed['decisions_verified'],
                observation_checks=recorded['observation_checks'],
                policy_view_checks=recorded['policy_view_checks'],
            )
        except Exception as exc:
            row.update(status='blocked', completed=False,
                       blocker=f'{type(exc).__name__}: {exc}')
        rows.append(row)
        if not row.get('completed'):
            break

    completed = sum(bool(r.get('completed')) for r in rows)
    report = {
        'purpose': 'deterministic_replay_prerequisite_for_offline_counterfactual_training',
        'deck_strength_evidence': False,
        'policy_skill_evidence': False,
        'policy_input_from_referee_hidden_state': False,
        'candidate': candidate_id,
        'planned': a.count,
        'completed': completed,
        'rows': rows,
        'note': (
            'Successful replay proves seed+deck+response history reconstructs the tested duel information sets. '
            'It does not authorize live rollout action selection from one realized hidden state.'
        ),
    }
    dump(ROOT/'reports/replay_probe.json', report)
    print(json.dumps({
        'planned': a.count,
        'completed': completed,
        'decisions_verified': sum(r.get('decisions_verified', 0) for r in rows),
    }))
    if completed != a.count:
        raise SystemExit(f'deterministic replay failed: completed {completed}/{a.count}')


if __name__ == '__main__':
    main()

"""Deterministic diagnostic for the held-out C-stack-overflow reproducer.

This module is deliberately referee-privileged. Its output is for engine/script
 debugging only and MUST NEVER be supplied to a learning policy or used as deck
 strength evidence.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import struct

from .announce import choose_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .learn_probe import run_training_game
from .learning import SparsePolicy
from .learning_pilot import LearningPilot
from .observation import (
    PublicTracker, observation_for, raw_query_field, parse_field_query,
    raw_query_card, parse_card_query,
    LOCATION_HAND, LOCATION_MZONE, LOCATION_SZONE, LOCATION_GRAVE,
    LOCATION_REMOVED, LOCATION_EXTRA,
)
from .ocgcore import Duel
from .pilot import StochasticLegalPilot
from .pilot_eval import _usable_candidates
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision

MSG_WIN = 5
TARGET_CANDIDATE = '593df70fb35282f5'
TARGET_SEED = 21101
TARGET_LEARNED_SEAT = 1


def _card_label(duel, code):
    return {'code': code, 'name': duel.names.get(code)} if code else {'code': code}


def _referee_card(duel, controller, location, sequence):
    try:
        info = parse_card_query(raw_query_card(duel, controller, location, sequence))
    except Exception as exc:
        return {'query_error': f'{type(exc).__name__}: {exc}'}
    if not info:
        return None
    out = dict(info)
    code = out.get('code')
    if code:
        out['name'] = duel.names.get(code)
    return out


def _referee_state(duel):
    """Privileged state snapshot for debugging only; never policy input."""
    field = parse_field_query(raw_query_field(duel))
    out = {
        'chains': [],
        'players': [],
    }
    for ch in field.get('chains', []):
        row = dict(ch)
        row['name'] = duel.names.get(row.get('code'))
        out['chains'].append(row)
    for p, src in enumerate(field['players']):
        row = {
            'player': p,
            'lp': src['lp'],
            'deck_count': src['deck_count'],
            'hand': [], 'mzone': [], 'szone': [], 'grave': [], 'removed': [], 'extra': [],
        }
        for i in range(src['hand_count']):
            row['hand'].append(_referee_card(duel, p, LOCATION_HAND, i))
        for slot in src['mzone']:
            if slot['present']:
                row['mzone'].append({'sequence': slot['sequence'], 'card': _referee_card(duel, p, LOCATION_MZONE, slot['sequence'])})
        for slot in src['szone']:
            if slot['present']:
                row['szone'].append({'sequence': slot['sequence'], 'card': _referee_card(duel, p, LOCATION_SZONE, slot['sequence'])})
        for i in range(src['grave_count']):
            row['grave'].append(_referee_card(duel, p, LOCATION_GRAVE, i))
        for i in range(src['removed_count']):
            row['removed'].append(_referee_card(duel, p, LOCATION_REMOVED, i))
        for i in range(src['extra_count']):
            row['extra'].append(_referee_card(duel, p, LOCATION_EXTRA, i))
        out['players'].append(row)
    return out


def _decision_debug(duel, decision):
    return {
        'kind': decision.kind,
        'player': decision.player,
        'minimum': decision.minimum,
        'maximum': decision.maximum,
        'cancelable': decision.cancelable,
        'meta': dict(decision.meta),
        'actions': [
            {
                'label': a.label,
                'response_hex': a.response.hex(),
                'description': a.description,
                'client_mode': a.client_mode,
                'extra': dict(a.extra),
                'card': None if a.card is None else {
                    **a.card.public(),
                    'name': duel.names.get(a.card.code),
                },
            }
            for a in decision.actions
        ],
        'cards': [
            {**c.public(), 'name': duel.names.get(c.code)} for c in decision.cards
        ],
    }


def _chosen_action(decision, response):
    for action in decision.actions:
        if action.response == response:
            return {
                'label': action.label,
                'description': action.description,
                'card_code': action.card.code if action.card else None,
                'card_controller': action.card.controller if action.card else None,
                'card_location': action.card.location if action.card else None,
                'card_sequence': action.card.sequence if action.card else None,
                'extra': dict(action.extra),
            }
    return None


def _train_policy(library, database, scripts, mapped, usable, policy_seed=20260906):
    train_pool = usable[:4]
    policy = SparsePolicy(seed=policy_seed, temperature=1.0, learning_rate=0.05)
    rows = []
    for game in range(16):
        left = game % len(train_pool)
        right = (left + 1) % len(train_pool)
        seat0, seat1 = train_pool[left], train_pool[right]
        if game % 2:
            seat0, seat1 = seat1, seat0
        seed = 11000 + game
        row = {'game': game, 'seed': seed, 'seat0': seat0[0], 'seat1': seat1[0]}
        row.update(run_training_game(
            library, database, scripts, (seat0[1], seat1[1]), mapped, policy, seed, 5000
        ))
        rows.append(row)
        if not row.get('completed'):
            raise UnsupportedInteraction(f'diagnostic training blocked in game {game}')
    if not policy.weights:
        raise UnsupportedInteraction('diagnostic training produced no weights')
    return policy, rows


def run_probe(library, database, scripts):
    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    policy, training = _train_policy(library, database, scripts, mapped, usable)
    target = next((d for cid, d in usable if cid == TARGET_CANDIDATE), None)
    if target is None:
        raise RuntimeError(f'target candidate {TARGET_CANDIDATE} is not usable')

    frozen = SparsePolicy(
        seed=TARGET_SEED * 1009 + TARGET_LEARNED_SEAT,
        temperature=policy.temperature,
        learning_rate=0.0,
        weights=dict(policy.weights),
    )
    learned = LearningPilot(frozen, seed=TARGET_SEED * 101 + 17 + TARGET_LEARNED_SEAT)
    baseline = StochasticLegalPilot(TARGET_SEED * 103 + 31 + TARGET_LEARNED_SEAT)
    tracker = PublicTracker()
    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    recent = deque(maxlen=16)
    report = {
        'purpose': 'engine_crash_diagnostic_only',
        'policy_input': False,
        'deck_strength_evidence': False,
        'candidate': TARGET_CANDIDATE,
        'seed': TARGET_SEED,
        'learned_seat': TARGET_LEARNED_SEAT,
        'training_games': len(training),
        'training_weight_count': len(policy.weights),
        'status': 'pending',
    }

    duel = Duel(library, database, scripts, seed=TARGET_SEED)
    try:
        for player in (0, 1):
            for index, cid in enumerate(target):
                duel.add(mapped[cid]['passcode'], player, sequence=index)
        duel.start()
        for step in range(5000):
            try:
                status, messages = duel.process()
            except Exception as exc:
                report.update(
                    status='reproduced_blocker',
                    blocker=f'{type(exc).__name__}: {exc}',
                    failing_process_call=duel.process_calls,
                    recent_decisions=list(recent),
                    engine_debug=duel.debug_snapshot(),
                )
                try:
                    report['referee_state_after_error'] = _referee_state(duel)
                except Exception as snap_exc:
                    report['referee_state_after_error_error'] = f'{type(snap_exc).__name__}: {snap_exc}'
                return report

            tracker.consume(messages)
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                report.update(status='unexpected_completion', winner=wins[0][1] if len(wins[0]) > 1 else None,
                              process_calls=duel.process_calls, recent_decisions=list(recent))
                return report

            decision = extract_decision(messages)
            if decision is None:
                if status != 2:
                    raise UnsupportedInteraction(f'engine stopped without decision: status={status}')
                continue

            observation = observation_for(duel, decision.player, tracker)
            prompt = policy_prompt_view(decision, observation)
            assert_no_hidden_code_leak(prompt, observation)
            if decision.kind == 'announce_card':
                code = choose_declarable(database, decision.meta['opcodes'], allowed_codes)
                response = struct.pack('<i', code)
                if decision.player == TARGET_LEARNED_SEAT:
                    learned.fallback_decisions += 1
            elif decision.player == TARGET_LEARNED_SEAT:
                response = learned.choose(decision, prompt, observation)
            else:
                response = baseline.choose(decision, observation)

            frame = {
                'step': step + 1,
                'process_call': duel.process_calls,
                'decision': _decision_debug(duel, decision),
                'chosen_response_hex': response.hex(),
                'chosen_action': _chosen_action(decision, response),
            }
            if frame['chosen_action'] and frame['chosen_action'].get('card_code'):
                frame['chosen_action']['card_name'] = duel.names.get(frame['chosen_action']['card_code'])
            try:
                frame['referee_state'] = _referee_state(duel)
            except Exception as exc:
                frame['referee_state_error'] = f'{type(exc).__name__}: {exc}'
            recent.append(frame)
            duel.respond(response)
        raise UnsupportedInteraction('diagnostic exceeded 5000 steps')
    finally:
        duel.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    a = p.parse_args()
    try:
        report = run_probe(a.library, a.database, a.scripts)
    except Exception as exc:
        report = {
            'purpose': 'engine_crash_diagnostic_only',
            'policy_input': False,
            'deck_strength_evidence': False,
            'status': 'probe_failed',
            'blocker': f'{type(exc).__name__}: {exc}',
        }
    dump(ROOT/'reports/crash_probe.json', report)
    print(json.dumps({
        'status': report.get('status'),
        'candidate': report.get('candidate'),
        'seed': report.get('seed'),
        'failing_process_call': report.get('failing_process_call'),
    }))
    # Diagnostic capture itself should not mask the canonical held-out gate.
    if report.get('status') == 'probe_failed':
        raise SystemExit('crash diagnostic failed before reproducer result')


if __name__ == '__main__':
    main()

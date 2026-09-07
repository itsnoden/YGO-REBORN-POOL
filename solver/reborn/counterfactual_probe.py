"""Prove that a recorded duel can be replayed to a decision and legally branched.

This probe is a prerequisite for offline counterfactual training.  It deliberately
changes one legal response after reconstructing the exact recorded information
set, then finishes the divergent duel with zero-prior stochastic legal pilots.
The branch result is diagnostic/training infrastructure only: it is never fed
back as a live action oracle, so one realized hidden deck order cannot become
policy-visible information.
"""
from __future__ import annotations

import argparse
import json

from .announce import enumerate_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .observation import PublicTracker, observation_for
from .pilot import StochasticLegalPilot
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision
from .replay_probe import (
    MSG_WIN, _decision_fingerprint, _load_deck, _record_game, _safe_fingerprint,
    _start_duel,
)


def _find_branch(history):
    for index, row in enumerate(history):
        actions = row['decision'].get('actions', ())
        responses = []
        for action in actions:
            value = action.get('response_hex')
            if value is not None and value not in responses:
                responses.append(value)
        original = row['response_hex']
        alternatives = [value for value in responses if value != original]
        if alternatives:
            return index, alternatives[0]
    raise UnsupportedInteraction('recorded duel contained no explicit alternative legal response')


def _run_branch(library, database, scripts, seed, deck, mapped, history,
                target_index, alternative_hex, budget):
    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    pilots = [
        StochasticLegalPilot(seed * 109 + 1009),
        StochasticLegalPilot(seed * 109 + 2027),
    ]
    tracker = PublicTracker()
    cursor = 0
    branched = False
    safe_checks = 0

    with _start_duel(library, database, scripts, seed, deck, mapped) as duel:
        for step in range(budget):
            status, messages = duel.process()
            tracker.consume(messages)
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                if not branched:
                    raise UnsupportedInteraction('duel ended before requested branch decision')
                return {
                    'winner': wins[0][1] if len(wins[0]) >= 2 else None,
                    'steps': step + 1,
                    'safe_checks': safe_checks,
                }

            decision = extract_decision(messages)
            if decision is not None:
                observation = observation_for(duel, decision.player, tracker)
                prompt = policy_prompt_view(decision, observation)
                assert_no_hidden_code_leak(prompt, observation)
                safe_checks += 1

                if not branched:
                    if cursor >= len(history):
                        raise UnsupportedInteraction('branch replay produced an unexpected pre-branch decision')
                    expected = history[cursor]
                    if _decision_fingerprint(decision) != expected['decision']:
                        raise UnsupportedInteraction(
                            f'pre-branch decision mismatch at index {cursor}: {decision.kind}/P{decision.player}'
                        )
                    if _safe_fingerprint(observation, prompt) != expected['safe_fingerprint']:
                        raise UnsupportedInteraction(
                            f'pre-branch information-set mismatch at index {cursor}'
                        )
                    if cursor < target_index:
                        response = bytes.fromhex(expected['response_hex'])
                    else:
                        legal_responses = {action.response.hex() for action in decision.actions}
                        if alternative_hex not in legal_responses:
                            raise UnsupportedInteraction(
                                f'planned branch response is no longer legal at index {cursor}'
                            )
                        response = bytes.fromhex(alternative_hex)
                        branched = True
                    cursor += 1
                elif decision.kind == 'announce_card':
                    legal_codes = enumerate_declarable(
                        database, decision.meta['opcodes'], allowed_codes
                    )
                    response = pilots[decision.player].choose_announce_card(legal_codes)
                else:
                    response = pilots[decision.player].choose(decision, observation)
                duel.respond(response)
                continue

            if status != 2:
                raise UnsupportedInteraction(
                    f'branched duel stopped without win/decision: status={status}, '
                    f'messages={[m[0] for m in messages if m]}'
                )
    raise UnsupportedInteraction(f'branched duel exceeded {budget} engine steps')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--seed', type=int, default=53000)
    p.add_argument('--budget', type=int, default=5000)
    a = p.parse_args()

    candidate_id, deck, mapped = _load_deck()
    report = {
        'purpose': 'offline_counterfactual_branch_prerequisite_only',
        'deck_strength_evidence': False,
        'policy_skill_evidence': False,
        'live_rollout_policy': False,
        'hidden_state_branch_outcome_used_as_live_input': False,
        'candidate': candidate_id,
        'seed': a.seed,
        'status': 'pending',
    }
    try:
        recorded = _record_game(
            a.library, a.database, a.scripts, a.seed, deck, mapped, a.budget
        )
        target_index, alternative_hex = _find_branch(recorded['history'])
        target = recorded['history'][target_index]
        branched = _run_branch(
            a.library, a.database, a.scripts, a.seed, deck, mapped,
            recorded['history'], target_index, alternative_hex, a.budget,
        )
        report.update(
            status='completed',
            completed=True,
            source_winner=recorded['winner'],
            source_decisions=len(recorded['history']),
            branch_decision_index=target_index,
            branch_kind=target['decision']['kind'],
            branch_player=target['decision']['player'],
            original_response_hex=target['response_hex'],
            alternative_response_hex=alternative_hex,
            branch_winner=branched['winner'],
            branch_steps=branched['steps'],
            branch_safe_checks=branched['safe_checks'],
        )
    except Exception as exc:
        report.update(status='blocked', completed=False,
                      blocker=f'{type(exc).__name__}: {exc}')

    dump(ROOT/'reports/counterfactual_probe.json', report)
    print(json.dumps({
        'status': report['status'],
        'branch_decision_index': report.get('branch_decision_index'),
        'branch_kind': report.get('branch_kind'),
        'source_winner': report.get('source_winner'),
        'branch_winner': report.get('branch_winner'),
    }))
    if not report.get('completed'):
        raise SystemExit('counterfactual branch prerequisite failed')


if __name__ == '__main__':
    main()

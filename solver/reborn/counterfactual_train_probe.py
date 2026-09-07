"""Smoke-test simulator-labeled offline counterfactual policy training.

The trainer uses no human card values or strategy labels.  It records a legal
source duel, chooses bounded explicit decision points without looking at their
outcomes, then replays the exact pre-decision history and evaluates every tested
legal action with matched zero-prior continuation pilots.  Only the acting
player's already-filtered observation/prompt becomes a policy feature.

A branch outcome comes from one realized hidden state, so it is training evidence
only.  It must never be queried as a live action oracle during held-out play.
"""
from __future__ import annotations

import argparse
import json
import random

from .counterfactual_probe import _run_branch
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .replay_probe import _load_deck, _record_game


def _unique_actions(target):
    """Return unique explicit response actions, preserving engine order."""
    out = []
    seen = set()
    for index, action in enumerate(target['decision'].get('actions', ())):
        response_hex = action.get('response_hex')
        if response_hex is None or response_hex in seen:
            continue
        seen.add(response_hex)
        out.append({
            'decision_action_index': index,
            'response_hex': response_hex,
        })
    return out


def _branchable_indices(history, max_options):
    out = []
    for index, target in enumerate(history):
        actions = _unique_actions(target)
        if 2 <= len(actions) <= max_options:
            safe = json.loads(target['safe_fingerprint'])
            prompt_actions = safe.get('prompt', {}).get('actions', ())
            if len(prompt_actions) != len(target['decision'].get('actions', ())):
                continue
            out.append(index)
    return out


def _outcome_value(winner, player):
    if winner == player:
        return 1
    if winner in (0, 1):
        return -1
    return 0


def _train_target(policy, library, database, scripts, seed, deck, mapped,
                  history, target_index, budget):
    target = history[target_index]
    safe = json.loads(target['safe_fingerprint'])
    observation = safe['observation']
    prompt = safe['prompt']
    player = int(target['decision']['player'])
    if observation.get('viewer') != player or prompt.get('player') != player:
        raise UnsupportedInteraction('recorded safe target belongs to wrong player')

    raw_actions = target['decision'].get('actions', ())
    prompt_actions = prompt.get('actions', ())
    if len(raw_actions) != len(prompt_actions):
        raise UnsupportedInteraction('safe/raw explicit action counts differ at training target')

    unique = _unique_actions(target)
    features = []
    branches = []
    for choice in unique:
        action_index = choice['decision_action_index']
        action_view = prompt_actions[action_index]
        option_features = policy.action_features(prompt, observation, action_view)
        branch = _run_branch(
            library, database, scripts, seed, deck, mapped, history,
            target_index, choice['response_hex'], budget,
        )
        features.append(option_features)
        branches.append({
            **choice,
            'label': action_view.get('label'),
            'winner': branch['winner'],
            'value_for_actor': _outcome_value(branch['winner'], player),
            'steps': branch['steps'],
            'safe_checks': branch['safe_checks'],
        })

    values = [row['value_for_actor'] for row in branches]
    best = max(values)
    best_indices = [i for i, value in enumerate(values) if value == best]
    before = policy.probabilities(features)
    updated = False
    preferred = None
    # A unique simulator-best action gives an unambiguous label. Tied outcomes
    # are deliberately skipped instead of injecting an arbitrary tie-break prior.
    if len(best_indices) == 1 and any(value < best for value in values):
        preferred = best_indices[0]
        policy.update_preference(features, preferred, scale=1.0)
        updated = True
    after = policy.probabilities(features)

    if updated and not after[preferred] > before[preferred]:
        raise UnsupportedInteraction('counterfactual preference update did not raise preferred probability')

    return {
        'decision_index': target_index,
        'kind': target['decision']['kind'],
        'player': player,
        'option_count': len(branches),
        'branches': branches,
        'unique_best': len(best_indices) == 1,
        'updated': updated,
        'preferred_option': preferred,
        'preferred_probability_before': before[preferred] if preferred is not None else None,
        'preferred_probability_after': after[preferred] if preferred is not None else None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--seed', type=int, default=54000)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--targets', type=int, default=2)
    p.add_argument('--max-options', type=int, default=3)
    p.add_argument('--policy-seed', type=int, default=20260907)
    a = p.parse_args()
    if a.targets < 1 or a.max_options < 2:
        raise ValueError('targets must be positive and max-options >= 2')

    candidate_id, deck, mapped = _load_deck()
    policy = SparsePolicy(seed=a.policy_seed, temperature=1.0, learning_rate=0.05)
    report = {
        'purpose': 'offline_counterfactual_training_smoke_only',
        'deck_strength_evidence': False,
        'pilot_skill_evidence': False,
        'external_strategy_priors': False,
        'live_rollout_policy': False,
        'hidden_state_used_as_policy_feature': False,
        'candidate': candidate_id,
        'seed': a.seed,
        'status': 'pending',
    }

    try:
        recorded = _record_game(
            a.library, a.database, a.scripts, a.seed, deck, mapped, a.budget
        )
        candidates = _branchable_indices(recorded['history'], a.max_options)
        if not candidates:
            raise UnsupportedInteraction('source duel has no bounded explicit counterfactual targets')

        # Sampling is independent of branch outcomes and card reputation.
        rng = random.Random(a.policy_seed ^ a.seed)
        rng.shuffle(candidates)
        selected = sorted(candidates[:a.targets])
        rows = [
            _train_target(
                policy, a.library, a.database, a.scripts, a.seed, deck, mapped,
                recorded['history'], index, a.budget,
            )
            for index in selected
        ]
        updates = sum(row['updated'] for row in rows)
        report.update(
            status='completed',
            completed=True,
            source_winner_debug_only=recorded['winner'],
            source_decisions=len(recorded['history']),
            branchable_targets=len(candidates),
            selected_targets=selected,
            targets_completed=len(rows),
            preference_updates=updates,
            weight_count=len(policy.weights),
            rows=rows,
            note=(
                'Labels come only from matched ocgcore branch outcomes. A realized hidden state affects '
                'the training label as simulation noise but is never present in policy features. '
                'This smoke run is not held-out pilot-skill or deck-strength evidence.'
            ),
        )
        policy.save(ROOT/'reports/counterfactual_policy_smoke.json')
    except Exception as exc:
        report.update(status='blocked', completed=False,
                      blocker=f'{type(exc).__name__}: {exc}')

    dump(ROOT/'reports/counterfactual_train_probe.json', report)
    print(json.dumps({
        'status': report['status'],
        'targets_completed': report.get('targets_completed', 0),
        'preference_updates': report.get('preference_updates', 0),
        'weight_count': report.get('weight_count', 0),
    }))
    if not report.get('completed'):
        raise SystemExit('offline counterfactual training smoke failed')


if __name__ == '__main__':
    main()

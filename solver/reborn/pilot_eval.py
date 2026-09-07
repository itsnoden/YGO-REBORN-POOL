"""Held-out pilot-skill evaluation without turning results into deck rankings.

Train a zero-prior policy on one generated-deck/seed set, freeze its weights,
then compare it with the zero-prior stochastic legal pilot on different generated
decks and disjoint seeds. Evaluation games are mirror matches (same deck on both
seats) and the learned pilot is swapped between seats for every seed, so deck
quality cannot masquerade as pilot quality.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import struct

from .announce import choose_declarable
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .learn_probe import run_training_game
from .learning import SparsePolicy
from .learning_pilot import LearningPilot
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .oracle import wilson_lower
from .pilot import StochasticLegalPilot
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision
from .search import validate

MSG_WIN = 5


def _usable_candidates(cards, mapped):
    candidates = json.loads((ROOT/'data/processed/candidates-20260906.json').read_text())['candidates']
    usable = []
    for candidate in candidates:
        deck = [cid for cid, n in candidate['main'].items() for _ in range(n)]
        if any(cid not in mapped for cid in deck):
            continue
        validate(deck, cards)
        usable.append((candidate['id'], deck))
    return usable


def run_eval_game(library, database, scripts, deck, mapped, frozen_policy,
                  learned_seat, seed, budget=5000):
    if learned_seat not in (0, 1):
        raise ValueError('learned_seat must be 0 or 1')
    allowed_codes = [entry['passcode'] for entry in mapped.values()]

    # Evaluation gets a fresh RNG but an exact frozen copy of the trained weights.
    eval_policy = SparsePolicy(
        seed=seed * 1009 + learned_seat,
        temperature=frozen_policy.temperature,
        learning_rate=0.0,
        weights=dict(frozen_policy.weights),
    )
    weights_before = dict(eval_policy.weights)
    learned = LearningPilot(eval_policy, seed=seed * 101 + 17 + learned_seat)
    baseline = StochasticLegalPilot(seed * 103 + 31 + learned_seat)
    tracker = PublicTracker()
    decision_types = Counter()
    row = {
        'seed': seed,
        'learned_seat': learned_seat,
        'baseline_seat': 1 - learned_seat,
        'status': 'pending',
        'steps': 0,
        'decisions': 0,
        'learned_decisions': 0,
        'learned_fallback_decisions': 0,
        'observation_checks': 0,
        'policy_view_checks': 0,
        'blocker': None,
    }

    with Duel(library, database, scripts, seed=seed) as duel:
        # Mirror deck: both pilots receive identical deck composition.
        for player in (0, 1):
            for index, cid in enumerate(deck):
                duel.add(mapped[cid]['passcode'], player, sequence=index)
        duel.start()

        for step in range(budget):
            status, messages = duel.process(); tracker.consume(messages)
            row['steps'] = step + 1
            wins = [m for m in messages if m and m[0] == MSG_WIN]
            if wins:
                winner = wins[0][1] if len(wins[0]) >= 2 else None
                row['winner_seat_debug_only'] = winner
                if winner == learned_seat:
                    row['learned_result'] = 'win'
                elif winner == 1 - learned_seat:
                    row['learned_result'] = 'loss'
                else:
                    row['learned_result'] = 'draw'
                row.update(
                    status='completed', completed=True,
                    learned_decisions=learned.learned_decisions,
                    learned_fallback_decisions=learned.fallback_decisions,
                    decision_types=dict(sorted(decision_types.items())),
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

                if decision.kind == 'announce_card':
                    code = choose_declarable(database, decision.meta['opcodes'], allowed_codes)
                    response = struct.pack('<i', code)
                    if decision.player == learned_seat:
                        learned.fallback_decisions += 1
                elif decision.player == learned_seat:
                    response = learned.choose(decision, prompt, observation)
                else:
                    response = baseline.choose(decision, observation)
                duel.respond(response)
                continue

            if status != 2:
                raise UnsupportedInteraction(
                    f'engine stopped without win/decision: status={status}, messages={[m[0] for m in messages if m]}'
                )
        else:
            raise UnsupportedInteraction(f'held-out evaluation exceeded {budget} engine steps')

    if eval_policy.weights != weights_before:
        raise UnsupportedInteraction('frozen evaluation policy mutated')
    if row.get('status') != 'completed':
        raise UnsupportedInteraction('held-out game did not complete')
    if row['observation_checks'] != row['decisions'] or row['policy_view_checks'] != row['decisions']:
        raise UnsupportedInteraction('not every held-out decision passed privacy observation/prompt checks')
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--train-games', type=int, default=16)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=2)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=11000)
    p.add_argument('--eval-seed', type=int, default=21000)
    p.add_argument('--policy-seed', type=int, default=20260906)
    a = p.parse_args()

    if a.train_games < 1 or a.train_decks < 2 or a.eval_decks < 1 or a.pairs_per_deck < 1:
        raise ValueError('invalid held-out evaluation sizes')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    required = a.train_decks + a.eval_decks
    if len(usable) < required:
        raise RuntimeError(f'need at least {required} usable candidates, found {len(usable)}')

    train_pool = usable[:a.train_decks]
    eval_pool = usable[a.train_decks:required]
    policy = SparsePolicy(seed=a.policy_seed, temperature=1.0, learning_rate=0.05)

    train_results = []
    for game in range(a.train_games):
        left = game % len(train_pool)
        right = (left + 1) % len(train_pool)
        if left == right:
            raise RuntimeError('training pool collapsed to one deck')
        seat0 = train_pool[left]
        seat1 = train_pool[right]
        if game % 2:
            seat0, seat1 = seat1, seat0
        seed = a.train_seed + game
        row = {
            'game': game,
            'seat0': seat0[0],
            'seat1': seat1[0],
            'seed': seed,
        }
        row.update(run_training_game(
            a.library, a.database, a.scripts,
            (seat0[1], seat1[1]), mapped, policy, seed, a.budget,
        ))
        if not row.get('completed'):
            raise UnsupportedInteraction(f'training game {game} did not complete')
        train_results.append(row)

    if not policy.weights:
        raise UnsupportedInteraction('training completed without nonzero policy weights')
    trained_weights = dict(policy.weights)
    policy_path = ROOT/'reports/heldout_policy_reborn.json'
    policy.save(policy_path)

    eval_results = []
    for deck_index, (candidate_id, deck) in enumerate(eval_pool):
        for pair in range(a.pairs_per_deck):
            seed = a.eval_seed + deck_index * 100 + pair
            # Same mirror deck and same engine seed; learned policy alternates seat.
            for learned_seat in (0, 1):
                row = {
                    'candidate': candidate_id,
                    'pair': pair,
                    'seed': seed,
                    'learned_seat': learned_seat,
                }
                row.update(run_eval_game(
                    a.library, a.database, a.scripts, deck, mapped,
                    policy, learned_seat, seed, a.budget,
                ))
                eval_results.append(row)

    if policy.weights != trained_weights:
        raise UnsupportedInteraction('training policy changed during frozen held-out evaluation')

    completed = sum(bool(r.get('completed')) for r in eval_results)
    learned_wins = sum(r.get('learned_result') == 'win' for r in eval_results)
    learned_losses = sum(r.get('learned_result') == 'loss' for r in eval_results)
    learned_draws = sum(r.get('learned_result') == 'draw' for r in eval_results)
    if completed != len(eval_results):
        raise UnsupportedInteraction(f'held-out evaluation completed {completed}/{len(eval_results)} games')

    decision_types = Counter()
    for row in eval_results:
        decision_types.update(row.get('decision_types', {}))
    raw_rate = learned_wins / completed if completed else 0.0
    report = {
        'purpose': 'heldout_pilot_skill_evaluation_only',
        'profile': 'reborn',
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'pilot_skill_evidence': 'preliminary_heldout',
        'external_strategy_priors': False,
        'training': {
            'games': len(train_results),
            'candidate_ids': [cid for cid, _ in train_pool],
            'seed_start': a.train_seed,
            'learned_decisions': sum(r.get('learned_decisions', 0) for r in train_results),
            'fallback_decisions': sum(r.get('fallback_decisions', 0) for r in train_results),
            'weight_count': len(policy.weights),
        },
        'evaluation': {
            'mirror_candidate_ids': [cid for cid, _ in eval_pool],
            'pairs_per_deck': a.pairs_per_deck,
            'games': completed,
            'seed_start': a.eval_seed,
            'learned_wins': learned_wins,
            'learned_losses': learned_losses,
            'learned_draws': learned_draws,
            'learned_win_rate': raw_rate,
            'learned_win_wilson95_lower': wilson_lower(learned_wins, completed),
            'learned_decisions': sum(r.get('learned_decisions', 0) for r in eval_results),
            'learned_fallback_decisions': sum(r.get('learned_fallback_decisions', 0) for r in eval_results),
            'observation_checks': sum(r.get('observation_checks', 0) for r in eval_results),
            'policy_view_checks': sum(r.get('policy_view_checks', 0) for r in eval_results),
            'decision_types': dict(sorted(decision_types.items())),
        },
        'policy_file': 'reports/heldout_policy_reborn.json',
        'train_results': train_results,
        'eval_results': eval_results,
        'note': (
            'Mirror decks and paired learned-seat swaps isolate pilot behavior from deck composition. '
            'This small held-out experiment is pilot-skill evidence only and must not rank decks.'
        ),
    }
    dump(ROOT/'reports/pilot_eval.json', report)
    print(json.dumps({
        'train_games': len(train_results),
        'eval_games': completed,
        'learned_wins': learned_wins,
        'learned_losses': learned_losses,
        'learned_draws': learned_draws,
        'learned_win_rate': raw_rate,
        'weight_count': len(policy.weights),
    }))


if __name__ == '__main__':
    main()

"""Held-out A/B for zero-prior historical-snapshot league training.

Control:
- one learning seat vs the fixed zero-prior stochastic-legal pilot.

Treatment:
- same one-seat learning setup, but after an initial bootstrap period the
  opponent alternates between the stochastic pilot and frozen historical
  snapshots of the learner.

Historical snapshots contain only weights learned from our own simulator
outcomes. They add no card values, archetype labels, tournament/meta knowledge,
human heuristics, or outside strategy priors.

The purpose is to reduce overfitting to one fixed stochastic opponent while
avoiding the gradient cancellation of a single shared policy controlling both
players.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json

from .announce import enumerate_declarable
from .credit_ab_eval import (
    _block_slice, _evaluate_arm, _paired_summary, _summarize_rows,
)
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .learning_pilot import LearningPilot
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .opponent_training_ab_eval import run_training_vs_stochastic
from .pilot import StochasticLegalPilot
from .pilot_eval import _usable_candidates, frozen_policy_copy
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision

MSG_WIN = 5


def run_training_vs_frozen(
    library, database, scripts, decks, mapped, learner_policy,
    frozen_opponent, learned_seat, seed, budget=5000,
):
    """Train one seat against an immutable historical policy snapshot."""
    if learned_seat not in (0, 1):
        raise ValueError('learned_seat must be 0 or 1')

    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    learned = LearningPilot(learner_policy, seed=seed * 101 + 17 + learned_seat)
    frozen = frozen_policy_copy(
        frozen_opponent, seed * 1009 + (1 - learned_seat)
    )
    frozen_before = dict(frozen.weights)
    opponent = LearningPilot(
        frozen, seed=seed * 103 + 31 + (1 - learned_seat)
    )
    tracker = PublicTracker()
    decision_types = Counter()
    row = {
        'seed': seed,
        'learned_seat': learned_seat,
        'status': 'pending',
        'steps': 0,
        'decisions': 0,
        'learned_decisions': 0,
        'complex_learned_decisions': 0,
        'fallback_decisions': 0,
        'opponent_fallback_decisions': 0,
        'observation_checks': 0,
        'policy_view_checks': 0,
        'blocker': None,
    }

    with Duel(library, database, scripts, seed=seed) as duel:
        for player, deck in enumerate(decks):
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
                learned.finish(winner)
                if frozen.weights != frozen_before:
                    raise UnsupportedInteraction(
                        'historical league opponent mutated during training'
                    )
                row.update(
                    status='completed',
                    completed=True,
                    winner_seat_debug_only=winner,
                    learned_result=(
                        'win' if winner == learned_seat
                        else 'loss' if winner == 1 - learned_seat
                        else 'draw'
                    ),
                    learned_decisions=learned.learned_decisions,
                    complex_learned_decisions=learned.complex_learned_decisions,
                    fallback_decisions=learned.fallback_decisions,
                    opponent_fallback_decisions=opponent.fallback_decisions,
                    fallback_kinds=dict(sorted(learned.fallback_kinds.items())),
                    opponent_fallback_kinds=dict(sorted(opponent.fallback_kinds.items())),
                    decision_types=dict(sorted(decision_types.items())),
                )
                return row

            decision = extract_decision(messages)
            if decision is not None:
                row['decisions'] += 1
                decision_types[decision.kind] += 1
                observation = observation_for(duel, decision.player, tracker)
                row['observation_checks'] += 1
                prompt = policy_prompt_view(decision, observation)
                assert_no_hidden_code_leak(prompt, observation)
                row['policy_view_checks'] += 1

                pilot = learned if decision.player == learned_seat else opponent
                if decision.kind == 'announce_card':
                    legal_codes = enumerate_declarable(
                        database, decision.meta['opcodes'], allowed_codes
                    )
                    response = pilot.choose_announce_card(
                        decision, prompt, observation, legal_codes
                    )
                else:
                    response = pilot.choose(decision, prompt, observation)
                duel.respond(response)
                continue

            if status != 2:
                raise UnsupportedInteraction(
                    f'league training stopped without win/decision: status={status}, '
                    f'messages={[m[0] for m in messages if m]}'
                )

    raise UnsupportedInteraction(
        f'league training exceeded {budget} engine steps'
    )


def _pair_for_game(train_pool, game):
    left = game % len(train_pool)
    right = (left + 1) % len(train_pool)
    seat0 = train_pool[left]
    seat1 = train_pool[right]
    if game % 2:
        seat0, seat1 = seat1, seat0
    return seat0, seat1


def _train_fixed(a, mapped, train_pool, block):
    policy_seed = a.policy_seed + block * 100003
    train_seed = a.train_seed + block * 1000
    policy = SparsePolicy(
        seed=policy_seed, temperature=1.0, learning_rate=0.05
    )
    rows = []
    for game in range(a.train_games):
        seat0, seat1 = _pair_for_game(train_pool, game)
        learned_seat = game % 2
        seed = train_seed + game
        row = {
            'game': game, 'seed': seed,
            'seat0': seat0[0], 'seat1': seat1[0],
            'learned_seat': learned_seat,
            'opponent_mode': 'stochastic_legal',
        }
        try:
            row.update(run_training_vs_stochastic(
                a.library, a.database, a.scripts,
                (seat0[1], seat1[1]), mapped, policy,
                learned_seat, seed, a.budget,
            ))
        except Exception as exc:
            row.update(
                status='blocked', completed=False,
                blocker=f'{type(exc).__name__}: {exc}',
            )
        rows.append(row)
        if not row.get('completed'):
            break
    complete = (
        len(rows) == a.train_games
        and all(r.get('completed') for r in rows)
        and bool(policy.weights)
    )
    return policy, rows, complete, train_seed, policy_seed


def _snapshot(policy, seed):
    return policy.__class__(
        seed=seed,
        temperature=policy.temperature,
        learning_rate=0.0,
        weights=dict(policy.weights),
    )


def _train_league(a, mapped, train_pool, block):
    policy_seed = a.policy_seed + block * 100003
    train_seed = a.train_seed + block * 1000
    policy = SparsePolicy(
        seed=policy_seed, temperature=1.0, learning_rate=0.05
    )
    rows = []
    snapshots = []

    for game in range(a.train_games):
        # Snapshot the learner BEFORE the next chunk starts. The initial chunk
        # bootstraps solely against stochastic legal play.
        if game > 0 and game % a.snapshot_interval == 0:
            snapshots.append(_snapshot(
                policy, policy_seed + 700000 + len(snapshots)
            ))

        seat0, seat1 = _pair_for_game(train_pool, game)
        learned_seat = game % 2
        seed = train_seed + game

        use_snapshot = bool(snapshots) and (game % 2 == 1)
        snapshot_index = (
            (game // 2) % len(snapshots)
            if use_snapshot else None
        )
        row = {
            'game': game, 'seed': seed,
            'seat0': seat0[0], 'seat1': seat1[0],
            'learned_seat': learned_seat,
            'opponent_mode': (
                'historical_snapshot' if use_snapshot
                else 'stochastic_legal'
            ),
            'snapshot_index': snapshot_index,
            'snapshots_available': len(snapshots),
        }

        try:
            if use_snapshot:
                row.update(run_training_vs_frozen(
                    a.library, a.database, a.scripts,
                    (seat0[1], seat1[1]), mapped, policy,
                    snapshots[snapshot_index],
                    learned_seat, seed, a.budget,
                ))
            else:
                row.update(run_training_vs_stochastic(
                    a.library, a.database, a.scripts,
                    (seat0[1], seat1[1]), mapped, policy,
                    learned_seat, seed, a.budget,
                ))
        except Exception as exc:
            row.update(
                status='blocked', completed=False,
                blocker=f'{type(exc).__name__}: {exc}',
            )

        rows.append(row)
        if not row.get('completed'):
            break

    complete = (
        len(rows) == a.train_games
        and all(r.get('completed') for r in rows)
        and bool(policy.weights)
    )
    return (
        policy, rows, complete, train_seed, policy_seed,
        len(snapshots),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--scripts', required=True)
    p.add_argument('--blocks', type=int, default=6)
    p.add_argument('--block-offset', type=int, default=0)
    p.add_argument('--train-games', type=int, default=64)
    p.add_argument('--train-decks', type=int, default=4)
    p.add_argument('--eval-decks', type=int, default=2)
    p.add_argument('--pairs-per-deck', type=int, default=4)
    p.add_argument('--snapshot-interval', type=int, default=16)
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=411000)
    p.add_argument('--eval-seed', type=int, default=421000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(
        a.blocks, a.train_games, a.train_decks, a.eval_decks,
        a.pairs_per_deck, a.snapshot_interval
    ) < 1:
        raise ValueError('league A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('league A/B requires at least two training decks')
    if a.snapshot_interval >= a.train_games:
        raise ValueError('snapshot interval must allow at least one snapshot')

    cards = {
        c['id']: c
        for c in json.loads((ROOT/'data/processed/cards.json').read_text())
    }
    mapped = {
        r['reborn_id']: r
        for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())
    }
    usable = _usable_candidates(cards, mapped)
    needed = (
        (a.block_offset + a.blocks)
        * (a.train_decks + a.eval_decks)
    )
    if len(usable) < needed:
        raise RuntimeError(
            'not enough usable candidates for league A/B'
        )

    blocks = []
    all_control_eval = []
    all_treatment_eval = []
    all_training_complete = True
    all_eval_complete = True
    all_frozen = True

    for block in range(a.blocks):
        cohort_block = a.block_offset + block
        train_pool, eval_pool = _block_slice(
            usable, cohort_block, a.train_decks, a.eval_decks
        )

        control, control_train, control_ok, train_seed, policy_seed = _train_fixed(
            a, mapped, train_pool, block
        )
        (
            treatment, treatment_train, treatment_ok,
            t_seed, t_policy_seed, snapshot_count,
        ) = _train_league(a, mapped, train_pool, block)

        if train_seed != t_seed or policy_seed != t_policy_seed:
            raise RuntimeError('league A/B seeds diverged')

        control_eval = []
        treatment_eval = []
        control_frozen = treatment_frozen = False
        eval_seed = a.eval_seed + block * 1000
        if control_ok and treatment_ok:
            control_eval, control_frozen, c_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, control, block
            )
            treatment_eval, treatment_frozen, t_eval_seed = _evaluate_arm(
                a, mapped, eval_pool, treatment, block
            )
            if c_eval_seed != t_eval_seed:
                raise RuntimeError('league A/B evaluation seeds diverged')
            eval_seed = c_eval_seed

        planned = a.eval_decks * a.pairs_per_deck * 2
        control_eval_ok = (
            len(control_eval) == planned
            and all(r.get('completed') for r in control_eval)
        )
        treatment_eval_ok = (
            len(treatment_eval) == planned
            and all(r.get('completed') for r in treatment_eval)
        )
        paired, pair_rows = _paired_summary(
            control_eval, treatment_eval
        )

        blocks.append({
            'block': block,
            'candidate_cohort_block': cohort_block,
            'train_candidate_ids': [cid for cid, _ in train_pool],
            'eval_candidate_ids': [cid for cid, _ in eval_pool],
            'train_seed_start': train_seed,
            'eval_seed_start': eval_seed,
            'policy_seed': policy_seed,
            'historical_snapshots_created': snapshot_count,
            'control': {
                'training_mode': 'one_seat_vs_fixed_stochastic_legal',
                'weight_count': len(control.weights),
                'training_complete': control_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
            },
            'treatment': {
                'training_mode': 'one_seat_vs_stochastic_and_historical_snapshots',
                'weight_count': len(treatment.weights),
                'training_complete': treatment_ok,
                'policy_frozen_during_evaluation': treatment_frozen,
                'training': _summarize_rows(treatment_train),
                'evaluation': _summarize_rows(treatment_eval),
            },
            'paired_outcomes': paired,
            'paired_results': pair_rows,
        })

        all_control_eval.extend(control_eval)
        all_treatment_eval.extend(treatment_eval)
        all_training_complete &= control_ok and treatment_ok
        all_eval_complete &= control_eval_ok and treatment_eval_ok
        all_frozen &= control_frozen and treatment_frozen

        if not (
            control_ok and treatment_ok
            and control_eval_ok and treatment_eval_ok
            and control_frozen and treatment_frozen
        ):
            break

    control_summary = _summarize_rows(all_control_eval)
    treatment_summary = _summarize_rows(all_treatment_eval)
    paired, paired_rows = _paired_summary(
        all_control_eval, all_treatment_eval
    )
    planned_total = (
        a.blocks * a.eval_decks
        * a.pairs_per_deck * 2
    )

    report = {
        'purpose': 'historical_snapshot_league_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'control_training': 'one learner seat vs fixed stochastic legal',
        'treatment_training': 'one learner seat vs stochastic + frozen self snapshots',
        'configuration': {
            'blocks': a.blocks,
            'block_offset': a.block_offset,
            'train_games_per_block_per_arm': a.train_games,
            'train_decks_per_block': a.train_decks,
            'eval_decks_per_block': a.eval_decks,
            'pairs_per_eval_deck': a.pairs_per_deck,
            'snapshot_interval': a.snapshot_interval,
            'planned_eval_games_per_arm': planned_total,
        },
        'control': control_summary,
        'treatment': treatment_summary,
        'treatment_minus_control_score_rate': (
            treatment_summary['learned_score_rate']
            - control_summary['learned_score_rate']
            if treatment_summary['learned_score_rate'] is not None
            and control_summary['learned_score_rate'] is not None
            else None
        ),
        'paired_outcomes': paired,
        'paired_results': paired_rows,
        'all_training_complete': all_training_complete,
        'all_evaluation_complete': all_eval_complete,
        'all_policies_frozen': all_frozen,
        'blocks': blocks,
        'note': (
            'Pilot-skill evidence only. Historical opponents are frozen copies '
            'of the solver own earlier weights and add no external strategy '
            'information. Held-out mirror deck identities are not rankings.'
        ),
    }
    dump(ROOT/'reports/league_training_ab.json', report)
    print(json.dumps({
        'eval_per_arm': control_summary['completed'],
        'control_score_rate': control_summary['learned_score_rate'],
        'treatment_score_rate': treatment_summary['learned_score_rate'],
        'delta': report['treatment_minus_control_score_rate'],
        'paired': paired,
        'control_fallback': control_summary['fallback_decisions'],
        'treatment_fallback': treatment_summary['fallback_decisions'],
    }))

    if not all_training_complete:
        raise SystemExit('league A/B training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('league A/B mutated a frozen evaluation policy')
    if not all_eval_complete:
        raise SystemExit('league A/B evaluation did not complete cleanly')
    if (
        control_summary['completed'] != planned_total
        or treatment_summary['completed'] != planned_total
    ):
        raise SystemExit('league A/B did not complete all held-out games')


if __name__ == '__main__':
    main()

"""Held-out A/B for asymmetric fixed-opponent pilot training.

Canonical training currently lets one shared policy control both players and
updates both sides from the terminal outcome. In a symmetric zero-sum setting,
shared-policy gradients can oppose each other and obscure whether the policy is
actually getting better at winning.

This treatment trains only one learning seat per duel against a fixed
zero-prior stochastic-legal opponent, alternating the learning seat across games.
The held-out evaluation protocol is unchanged.

This is a generic self-play/curriculum design experiment. It introduces no card
values, archetype labels, human heuristics, tournament/meta data, or historical
strategy priors.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json

from .announce import enumerate_declarable
from .credit_ab_eval import (
    _block_slice, _evaluate_arm, _paired_summary, _summarize_rows, _train_arm,
)
from .effects import UnsupportedInteraction
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .learning_pilot import LearningPilot
from .observation import PublicTracker, observation_for
from .ocgcore import Duel
from .pilot import StochasticLegalPilot
from .pilot_eval import _usable_candidates
from .policy_view import policy_prompt_view, assert_no_hidden_code_leak
from .protocol_extra import extract_decision

MSG_WIN = 5


def run_training_vs_stochastic(
    library, database, scripts, decks, mapped, policy,
    learned_seat, seed, budget=5000,
):
    if learned_seat not in (0, 1):
        raise ValueError('learned_seat must be 0 or 1')

    allowed_codes = [entry['passcode'] for entry in mapped.values()]
    learned = LearningPilot(policy, seed=seed * 101 + 17 + learned_seat)
    baseline = StochasticLegalPilot(seed * 103 + 31 + learned_seat)
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
        'fallback_kinds': {},
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
                    fallback_kinds=dict(sorted(learned.fallback_kinds.items())),
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

                if decision.kind == 'announce_card':
                    legal_codes = enumerate_declarable(
                        database, decision.meta['opcodes'], allowed_codes
                    )
                    if decision.player == learned_seat:
                        response = learned.choose_announce_card(
                            decision, prompt, observation, legal_codes
                        )
                    else:
                        response = baseline.choose_announce_card(legal_codes)
                elif decision.player == learned_seat:
                    response = learned.choose(decision, prompt, observation)
                else:
                    response = baseline.choose(decision, observation)

                duel.respond(response)
                continue

            if status != 2:
                raise UnsupportedInteraction(
                    f'asymmetric training stopped without win/decision: '
                    f'status={status}, messages={[m[0] for m in messages if m]}'
                )

    raise UnsupportedInteraction(
        f'asymmetric training exceeded {budget} engine steps'
    )


def _train_treatment(a, mapped, train_pool, block):
    policy_seed = a.policy_seed + block * 100003
    train_seed = a.train_seed + block * 1000
    policy = SparsePolicy(
        seed=policy_seed, temperature=1.0, learning_rate=0.05
    )
    rows = []

    for game in range(a.train_games):
        left = game % len(train_pool)
        right = (left + 1) % len(train_pool)
        seat0 = train_pool[left]
        seat1 = train_pool[right]
        if game % 2:
            seat0, seat1 = seat1, seat0

        learned_seat = game % 2
        seed = train_seed + game
        row = {
            'game': game,
            'seed': seed,
            'seat0': seat0[0],
            'seat1': seat1[0],
            'learned_seat': learned_seat,
        }
        try:
            row.update(run_training_vs_stochastic(
                a.library, a.database, a.scripts,
                (seat0[1], seat1[1]), mapped, policy,
                learned_seat, seed, a.budget,
            ))
        except Exception as exc:
            row.update(
                status='blocked',
                completed=False,
                blocker=f'{type(exc).__name__}: {exc}',
            )
        rows.append(row)
        if not row.get('completed'):
            break

    complete = len(rows) == a.train_games and all(
        r.get('completed') for r in rows
    )
    if not policy.weights:
        complete = False
    return policy, rows, complete, train_seed, policy_seed


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
    p.add_argument('--budget', type=int, default=5000)
    p.add_argument('--train-seed', type=int, default=371000)
    p.add_argument('--eval-seed', type=int, default=381000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(a.blocks, a.train_games, a.train_decks, a.eval_decks, a.pairs_per_deck) < 1:
        raise ValueError('opponent-training A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('opponent-training A/B requires at least two training decks')

    cards = {c['id']: c for c in json.loads((ROOT/'data/processed/cards.json').read_text())}
    mapped = {r['reborn_id']: r for r in json.loads((ROOT/'data/processed/engine_cards.json').read_text())}
    usable = _usable_candidates(cards, mapped)
    needed = (a.block_offset + a.blocks) * (a.train_decks + a.eval_decks)
    if len(usable) < needed:
        raise RuntimeError(
            f'opponent-training A/B needs candidates through block '
            f'{a.block_offset + a.blocks - 1}, found only {len(usable)}'
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

        control, control_train, control_ok, train_seed, policy_seed = _train_arm(
            a, mapped, train_pool, block, SparsePolicy
        )
        treatment, treatment_train, treatment_ok, t_seed, t_policy_seed = _train_treatment(
            a, mapped, train_pool, block
        )
        if train_seed != t_seed or policy_seed != t_policy_seed:
            raise RuntimeError('opponent-training A/B seeds diverged')

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
                raise RuntimeError('opponent-training A/B evaluation seeds diverged')
            eval_seed = c_eval_seed

        planned = a.eval_decks * a.pairs_per_deck * 2
        control_eval_ok = len(control_eval) == planned and all(
            r.get('completed') for r in control_eval
        )
        treatment_eval_ok = len(treatment_eval) == planned and all(
            r.get('completed') for r in treatment_eval
        )
        paired, pair_rows = _paired_summary(control_eval, treatment_eval)

        blocks.append({
            'block': block,
            'candidate_cohort_block': cohort_block,
            'train_candidate_ids': [cid for cid, _ in train_pool],
            'eval_candidate_ids': [cid for cid, _ in eval_pool],
            'train_seed_start': train_seed,
            'eval_seed_start': eval_seed,
            'policy_seed': policy_seed,
            'control': {
                'training_mode': 'shared_policy_both_players',
                'weight_count': len(control.weights),
                'training_complete': control_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
            },
            'treatment': {
                'training_mode': 'one_learning_seat_vs_fixed_stochastic_legal',
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
            control_ok and treatment_ok and control_eval_ok and treatment_eval_ok
            and control_frozen and treatment_frozen
        ):
            break

    control_summary = _summarize_rows(all_control_eval)
    treatment_summary = _summarize_rows(all_treatment_eval)
    paired, paired_rows = _paired_summary(all_control_eval, all_treatment_eval)
    planned_total = a.blocks * a.eval_decks * a.pairs_per_deck * 2

    report = {
        'purpose': 'fixed_opponent_training_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'training_games_per_block_per_arm': a.train_games,
        'control_training': 'shared policy controls both players',
        'treatment_training': 'one learning seat vs fixed stochastic legal opponent',
        'configuration': {
            'blocks': a.blocks,
            'block_offset': a.block_offset,
            'train_decks_per_block': a.train_decks,
            'eval_decks_per_block': a.eval_decks,
            'pairs_per_eval_deck': a.pairs_per_deck,
            'planned_eval_games_per_arm': planned_total,
            'train_seed_base': a.train_seed,
            'eval_seed_base': a.eval_seed,
            'policy_seed_base': a.policy_seed,
        },
        'control': control_summary,
        'treatment': treatment_summary,
        'treatment_minus_control_win_rate': (
            treatment_summary['learned_win_rate'] - control_summary['learned_win_rate']
            if treatment_summary['learned_win_rate'] is not None
            and control_summary['learned_win_rate'] is not None else None
        ),
        'treatment_minus_control_score_rate': (
            treatment_summary['learned_score_rate'] - control_summary['learned_score_rate']
            if treatment_summary['learned_score_rate'] is not None
            and control_summary['learned_score_rate'] is not None else None
        ),
        'paired_outcomes': paired,
        'paired_results': paired_rows,
        'all_training_complete': all_training_complete,
        'all_evaluation_complete': all_eval_complete,
        'all_policies_frozen': all_frozen,
        'blocks': blocks,
        'note': (
            'Pilot-skill evidence only. Treatment changes only who controls the '
            'opposing training seat. Evaluation is still held-out mirror play '
            'against the zero-prior stochastic legal baseline.'
        ),
    }
    dump(ROOT/'reports/opponent_training_ab.json', report)
    print(json.dumps({
        'blocks_completed': len(blocks),
        'eval_per_arm': control_summary['completed'],
        'eval_planned_per_arm': planned_total,
        'control_score_rate': control_summary['learned_score_rate'],
        'treatment_score_rate': treatment_summary['learned_score_rate'],
        'treatment_minus_control_score_rate': report['treatment_minus_control_score_rate'],
        'paired': paired,
        'control_fallback': control_summary['fallback_decisions'],
        'treatment_fallback': treatment_summary['fallback_decisions'],
    }))

    if not all_training_complete:
        raise SystemExit('opponent-training A/B training did not complete cleanly')
    if not all_frozen:
        raise SystemExit('opponent-training A/B mutated a frozen policy')
    if not all_eval_complete:
        raise SystemExit('opponent-training A/B evaluation did not complete cleanly')
    if control_summary['completed'] != planned_total or treatment_summary['completed'] != planned_total:
        raise SystemExit('opponent-training A/B did not complete all held-out games')


if __name__ == '__main__':
    main()

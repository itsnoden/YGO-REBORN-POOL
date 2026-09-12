"""Held-out A/B for zero-prior rule-text tag generalization.

A policy based only on card IDs cannot generalize a learned preference to a card
identity it has never seen in training.  This treatment adds neutral lexical
features derived mechanically from the current official card text screening
already maintained by the solver.

Examples of screening tags include draw, search, discard, Special Summon,
tribute, banish, negate, restriction, and repeatable-candidate.  The tags do NOT
assign power or strategic value; they only describe words/clauses detected in
the card's authoritative rules text. Their weights start at zero and can gain
value only from our own simulator outcomes.

The treatment adds:
- action-card rule tags x action label;
- selected-card rule tags x selection label;
- PUBLIC opponent-field rule tags x action anchors.

It never exposes hidden cards and uses no tournament/meta/community strategy.
"""
from __future__ import annotations

import argparse
import json

from .credit_ab_eval import (
    _block_slice, _evaluate_arm, _paired_summary, _summarize_rows, _train_arm,
)
from .import_pool import ROOT, dump
from .learning import SparsePolicy
from .pilot_eval import _usable_candidates


def load_passcode_tags():
    """Map engine passcodes to the union of neutral screened rule-text tags."""
    screenings = {
        row['id']: tuple(row.get('tags', ()))
        for row in json.loads(
            (ROOT/'data/processed/screening.json').read_text()
        )
    }
    mapped = json.loads(
        (ROOT/'data/processed/engine_cards.json').read_text()
    )
    out = {}
    for row in mapped:
        code = int(row['passcode'])
        tags = screenings.get(row['reborn_id'], ())
        if not tags:
            continue
        out.setdefault(code, set()).update(tags)
    return {
        code: tuple(sorted(tags))
        for code, tags in out.items()
    }


class RuleTagContextPolicy(SparsePolicy):
    """Canonical policy plus zero-prior official-rule-text tag features."""

    def __init__(self, *args, passcode_tags=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.passcode_tags = (
            load_passcode_tags()
            if passcode_tags is None
            else {
                int(code): tuple(tags)
                for code, tags in passcode_tags.items()
            }
        )

    @staticmethod
    def _unique(values):
        return tuple(dict.fromkeys(values))

    def _tags(self, code):
        if code is None:
            return ()
        return self.passcode_tags.get(int(code), ())

    def _opponent_public_tags(self, observation):
        viewer = observation['viewer']
        opponent = observation['players'][1 - viewer]
        tags = []
        for zone_name in ('mzone', 'szone'):
            for slot in opponent.get(zone_name, ()):
                if not slot.get('present'):
                    continue
                card = slot.get('card') or {}
                code = card.get('code')
                if code is None:
                    continue
                tags.extend(self._tags(code))
        return self._unique(tags)

    def _opponent_context_cross(self, observation, anchors):
        anchors = self._unique(anchors)
        return tuple(
            f'opp_rule_ctx:{tag}|{anchor}'
            for tag in self._opponent_public_tags(observation)
            for anchor in anchors
        )

    def action_features(self, prompt, observation, action):
        features = list(super().action_features(prompt, observation, action))
        kind = prompt['kind']
        label = action.get('label', 'unknown')
        anchors = [f'kind_label:{kind}|{label}']

        card = action.get('card')
        code = card.get('code') if card else None
        if code is not None:
            anchors.append(f'card_label:{code}|{label}')
            for tag in self._tags(code):
                token = f'action_rule_tag:{tag}|{label}'
                features.append(token)
                anchors.append(token)

        if action.get('description') is not None:
            anchors.append(f'desc_label:{action["description"]}|{label}')

        features.extend(
            self._opponent_context_cross(observation, anchors)
        )
        return tuple(features)

    def card_features(self, prompt, observation, card):
        features = list(super().card_features(prompt, observation, card))
        anchors = [f'kind_label:{prompt["kind"]}|select_card']
        code = card.get('code')
        if code is not None:
            anchors.append(f'card_label:{code}|select_card')
            for tag in self._tags(code):
                token = f'selected_rule_tag:{tag}|select_card'
                features.append(token)
                anchors.append(token)
        features.extend(
            self._opponent_context_cross(observation, anchors)
        )
        return tuple(features)

    def complex_features(self, prompt, observation, option):
        features = list(super().complex_features(prompt, observation, option))
        kind = prompt['kind']
        label = option.get('label', 'complex')
        anchors = [f'kind_label:{kind}|{label}']

        for card in option.get('selected_cards', ()):
            code = card.get('code')
            if code is None:
                continue
            anchors.append(f'card_label:{code}|{label}')
            for tag in self._tags(code):
                token = f'selected_rule_tag:{tag}|{label}'
                features.append(token)
                anchors.append(token)

        features.extend(
            self._opponent_context_cross(observation, anchors)
        )
        return tuple(features)


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
    p.add_argument('--train-seed', type=int, default=451000)
    p.add_argument('--eval-seed', type=int, default=461000)
    p.add_argument('--policy-seed', type=int, default=20260911)
    a = p.parse_args()

    if min(
        a.blocks, a.train_games, a.train_decks,
        a.eval_decks, a.pairs_per_deck
    ) < 1:
        raise ValueError('rule-tag A/B counts must all be positive')
    if a.train_decks < 2:
        raise ValueError('rule-tag A/B requires at least two training decks')

    cards = {
        c['id']: c
        for c in json.loads(
            (ROOT/'data/processed/cards.json').read_text()
        )
    }
    mapped = {
        r['reborn_id']: r
        for r in json.loads(
            (ROOT/'data/processed/engine_cards.json').read_text()
        )
    }
    usable = _usable_candidates(cards, mapped)
    needed = (
        (a.block_offset + a.blocks)
        * (a.train_decks + a.eval_decks)
    )
    if len(usable) < needed:
        raise RuntimeError('not enough candidates for rule-tag A/B')

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
        treatment, treatment_train, treatment_ok, t_seed, t_policy_seed = _train_arm(
            a, mapped, train_pool, block, RuleTagContextPolicy
        )
        if train_seed != t_seed or policy_seed != t_policy_seed:
            raise RuntimeError('rule-tag A/B seeds diverged')

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
                raise RuntimeError('rule-tag A/B eval seeds diverged')
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
            'control': {
                'policy': 'canonical_sparse_v2',
                'weight_count': len(control.weights),
                'training_complete': control_ok,
                'policy_frozen_during_evaluation': control_frozen,
                'training': _summarize_rows(control_train),
                'evaluation': _summarize_rows(control_eval),
            },
            'treatment': {
                'policy': 'canonical_plus_official_rule_text_tags',
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
        'purpose': 'official_rule_text_tag_heldout_pilot_ab_only',
        'profile': 'reborn',
        'external_strategy_priors': False,
        'deck_ranking_evidence': False,
        'strength_evidence_for_decks': False,
        'canonical_learner_modified': False,
        'tag_source': 'mechanical screening of current official rules text',
        'tag_values_are_strategy_priors': False,
        'control_policy': 'canonical sparse policy',
        'treatment_policy': (
            'canonical + action/selection rule tags + public opponent-field rule-tag context'
        ),
        'configuration': {
            'blocks': a.blocks,
            'block_offset': a.block_offset,
            'train_games_per_block_per_arm': a.train_games,
            'train_decks_per_block': a.train_decks,
            'eval_decks_per_block': a.eval_decks,
            'pairs_per_eval_deck': a.pairs_per_deck,
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
            'Tags are neutral lexical descriptors of authoritative card text, '
            'not strength labels. All strategic weights start at zero and are '
            'learned only from simulator outcomes. Candidate outcomes are not '
            'deck rankings.'
        ),
    }
    dump(ROOT/'reports/rule_tag_context_ab.json', report)
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
        raise SystemExit('rule-tag A/B training did not complete')
    if not all_frozen:
        raise SystemExit('rule-tag A/B mutated frozen evaluation policy')
    if not all_eval_complete:
        raise SystemExit('rule-tag A/B evaluation incomplete')
    if (
        control_summary['completed'] != planned_total
        or treatment_summary['completed'] != planned_total
    ):
        raise SystemExit('rule-tag A/B did not complete all held-out games')


if __name__ == '__main__':
    main()

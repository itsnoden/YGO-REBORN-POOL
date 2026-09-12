"""Policy-driven legal pilot that learns only from filtered self-play data."""
from __future__ import annotations

from collections import Counter
import struct

from .effects import UnsupportedInteraction
from .learning import PolicyStep
from .legal_options import enumerate_policy_options
from .protocol import encode_card_selection
from .pilot import StochasticLegalPilot


class LearningPilot:
    def __init__(self, policy, seed=1, max_complex_options=512):
        self.policy = policy
        self.fallback = StochasticLegalPilot(seed)
        self.max_complex_options = int(max_complex_options)
        self.steps = []
        self.learned_decisions = 0
        self.complex_learned_decisions = 0
        self.fallback_decisions = 0
        self.fallback_kinds = Counter()

    def reset_episode(self):
        self.steps = []
        self.learned_decisions = 0
        self.complex_learned_decisions = 0
        self.fallback_decisions = 0
        self.fallback_kinds = Counter()

    def _learn(self, player, option_features):
        if not option_features:
            raise UnsupportedInteraction('learning pilot received empty option set')
        chosen = self.policy.sample(option_features)
        self.steps.append(PolicyStep(player, option_features, chosen))
        self.learned_decisions += 1
        return chosen


    def _choose_large_card_selection(self, decision, prompt, observation):
        """Factorize a large legal subset choice into bounded internal decisions.

        Select-card legality is combinatorial only in which distinct cards are
        selected and in the min/max/cancel bounds. When complete subset
        enumeration exceeds max_complex_options, choose the subset
        autoregressively instead of handing the whole strategic choice to the
        random fallback.

        Each internal pick uses only the same filtered card views already
        available to the acting player. The final response is encoded once and
        sent to the referee exactly like an ordinary select-card response.
        """
        cards = list(prompt.get('cards', ()))
        if len(cards) != len(decision.cards):
            raise UnsupportedInteraction(
                'large select-card filtered/referee card counts differ'
            )
        selected = []

        while len(selected) < decision.maximum:
            option_features = []
            option_kinds = []

            if not selected and decision.cancelable:
                features = tuple(self.policy.action_features(
                    prompt, observation, {'label': 'cancel_selection'}
                )) + (
                    'large_select:cancel',
                    'large_select_selected_count:0',
                )
                option_features.append(features)
                option_kinds.append(('cancel', None))

            if len(selected) >= decision.minimum:
                features = tuple(self.policy.action_features(
                    prompt, observation, {'label': 'finish_selection'}
                )) + (
                    'large_select:finish',
                    f'large_select_selected_count:{len(selected)}',
                )
                option_features.append(features)
                option_kinds.append(('finish', None))

            for index, card in enumerate(cards):
                if index in selected:
                    continue
                features = tuple(self.policy.card_features(
                    prompt, observation, card
                )) + (
                    'large_select:pick',
                    f'large_select_selected_count:{len(selected)}',
                )
                option_features.append(features)
                option_kinds.append(('pick', index))

            if not option_features:
                break

            chosen = self._learn(decision.player, option_features)
            self.complex_learned_decisions += 1
            kind, index = option_kinds[chosen]

            if kind == 'cancel':
                return encode_card_selection(decision, None)
            if kind == 'finish':
                break
            selected.append(index)

        if len(selected) < decision.minimum:
            raise UnsupportedInteraction(
                'large select-card factorization ended below minimum'
            )
        if len(selected) > decision.maximum:
            raise UnsupportedInteraction(
                'large select-card factorization exceeded maximum'
            )
        return encode_card_selection(decision, selected)

    def choose_announce_card(self, decision, prompt, observation, legal_codes):
        """Learn a declaration from a complete database-verified Reborn legal set.

        Card codes here are legal public choices produced by the announce-card
        legality evaluator, not hidden referee state or strategic annotations.
        """
        if decision.kind != 'announce_card':
            raise UnsupportedInteraction('announce-card chooser received wrong decision kind')
        if prompt.get('player') != decision.player or observation.get('viewer') != decision.player:
            raise UnsupportedInteraction('learning pilot received mismatched player data')
        codes = tuple(int(code) for code in legal_codes)
        if not codes:
            raise UnsupportedInteraction('announce-card chooser received no legal codes')
        option_features = [
            self.policy.action_features(
                prompt, observation,
                {'label': 'announce_card', 'card': {'code': code}},
            )
            for code in codes
        ]
        chosen = self._learn(decision.player, option_features)
        self.complex_learned_decisions += 1
        return struct.pack('<i', codes[chosen])

    def choose(self, decision, prompt, observation):
        if prompt.get('player') != decision.player or observation.get('viewer') != decision.player:
            raise UnsupportedInteraction('learning pilot received mismatched player data')

        # First expand implicit combinatorial response families when (and only
        # when) their complete legal action set is bounded. Raw legality helpers
        # are used inside legal_options.py but never enter the option view or
        # policy features.
        complex_options = enumerate_policy_options(
            decision, prompt, max_options=self.max_complex_options
        )
        if complex_options is not None:
            option_features = [
                self.policy.complex_features(prompt, observation, option.view)
                for option in complex_options
            ]
            chosen = self._learn(decision.player, option_features)
            self.complex_learned_decisions += 1
            return complex_options[chosen].response

        # Large select-card subset spaces are exactly factorable into a sequence
        # of safe pick/finish decisions. This avoids random fallback without
        # truncating the legal subset space.
        if decision.kind == 'select_card':
            return self._choose_large_card_selection(
                decision, prompt, observation
            )

        # Most strategic engine prompts already expose an explicit legal action
        # list. Score only the filtered policy-view actions; use the raw Decision
        # solely after selection to retrieve the opaque response bytes.
        if decision.actions:
            if len(prompt.get('actions', ())) != len(decision.actions):
                raise UnsupportedInteraction('filtered action count differs from referee action count')
            option_features = [
                self.policy.action_features(prompt, observation, action)
                for action in prompt['actions']
            ]
            chosen = self._learn(decision.player, option_features)
            return decision.actions[chosen].response

        # Unbounded combinatorial prompts stay on the seeded legal fallback. The
        # information-safe observation, not raw prompt/referee metadata, is sent
        # to that fallback. Track the exact remaining families so future work can
        # target the real uncovered strategic surface.
        self.fallback_decisions += 1
        self.fallback_kinds[decision.kind] += 1
        return self.fallback.choose(decision, observation)

    def finish(self, winner):
        self.policy.update_episode(self.steps, winner)

"""From-scratch self-play policy with sparse contextual REINFORCE updates.

No card values, deck archetypes, tournament priors or human heuristics are baked
in. Features are derived only from information-safe observations and filtered
legal prompts. Card/action preferences and card interactions can emerge only
from simulated outcomes.

This is infrastructure, not evidence that the pilot is strong. The duel backend
uses the user-confirmed YGO Reborn rules profile; training quality must still be
validated independently before any deck-strength conclusions are allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import random
from pathlib import Path


@dataclass
class PolicyStep:
    player: int
    option_features: list[tuple[str, ...]]
    chosen: int


class SparsePolicy:
    def __init__(self, seed=1, temperature=1.0, learning_rate=0.03, weights=None):
        self.rng = random.Random(seed)
        self.seed = seed
        self.temperature = float(temperature)
        self.learning_rate = float(learning_rate)
        self.weights = dict(weights or {})

    @staticmethod
    def _bucket(value, width, cap=8):
        value = int(value)
        if width <= 0: return str(value)
        b = max(-cap, min(cap, value // width))
        return str(b)

    def _state_features(self, observation):
        """Compact public/information-set state facts.

        These scalar features are also crossed with option-specific features
        below. Standalone state terms are retained for backwards compatibility,
        but by themselves they cancel between options in a softmax decision.
        """
        viewer = observation['viewer']; opp = 1 - viewer
        me = observation['players'][viewer]; them = observation['players'][opp]
        my_field = sum(s.get('present', False) for s in me['mzone'] + me['szone'])
        op_field = sum(s.get('present', False) for s in them['mzone'] + them['szone'])
        phase = observation.get('phase')
        turn_player = observation.get('turn_player')
        return (
            'bias',
            f'phase:{phase}',
            f'turn_side:{"self" if turn_player == viewer else "opp" if turn_player in (0,1) else "unknown"}',
            f'turn_number:{self._bucket(observation.get("turn_number", 0), 2)}',
            f'chain_depth:{self._bucket(len(observation.get("chains", ())), 1)}',
            f'lp_diff:{self._bucket(me["lp"] - them["lp"], 1000)}',
            f'hand_diff:{self._bucket(me["hand_count"] - them["hand_count"], 1)}',
            f'field_diff:{self._bucket(my_field - op_field, 1)}',
            f'grave_diff:{self._bucket(me["grave_count"] - them["grave_count"], 2)}',
            f'removed_diff:{self._bucket(me["removed_count"] - them["removed_count"], 2)}',
            f'deck_diff:{self._bucket(me["deck_count"] - them["deck_count"], 4)}',
        )

    def _known_card_context(self, observation):
        """Return only card identities already present in the safe observation.

        The observation layer is the hidden-information boundary. This method
        never queries the referee and never accepts raw Decision data. Opponent
        hidden hand/field/Extra Deck entries therefore have no ``code`` here and
        cannot become policy features.
        """
        viewer = observation['viewer']
        features = []
        for player, row in enumerate(observation['players']):
            rel = 'self' if player == viewer else 'opp'

            for zone_name in ('mzone', 'szone'):
                for slot in row.get(zone_name, ()):
                    if not slot.get('present'):
                        continue
                    card = slot.get('card') or {}
                    code = card.get('code')
                    if code is None:
                        continue
                    features.append(f'known:{rel}|{zone_name}|{code}')
                    position = card.get('position', slot.get('position'))
                    if position is not None:
                        features.append(f'known_pos:{rel}|{zone_name}|{code}|{position}')

            for zone_name in ('hand', 'grave', 'removed', 'extra'):
                for card in row.get(zone_name, ()):
                    if not card:
                        continue
                    code = card.get('code')
                    if code is not None:
                        features.append(f'known:{rel}|{zone_name}|{code}')

        for chain in observation.get('chains', ()):
            code = chain.get('code')
            controller = chain.get('handler_controller')
            if code is None:
                continue
            rel = 'self' if controller == viewer else 'opp' if controller in (0, 1) else 'unknown'
            features.append(f'known_chain:{rel}|{code}')
        return tuple(features)

    @staticmethod
    def _unique(values):
        return tuple(dict.fromkeys(values))

    def _conditioned_features(self, state, known_cards, anchors, card_anchors=()):
        """Create sparse state x action interactions without strategic priors.

        A linear softmax cannot react to a state term that is identical for every
        option: that term cancels from all logits. Crossing safe state facts with
        option-specific anchors lets self-play learn conditional decisions such
        as choosing one legal card when another known card is present. The model
        is still zero-prior: the identities have no initial values.
        """
        anchors = self._unique(anchors)
        card_anchors = self._unique(card_anchors)
        out = []
        for context in state:
            if context == 'bias':
                continue
            for anchor in anchors:
                out.append(f'x:{context}|{anchor}')

        # Known-card context is potentially larger than the scalar state. When
        # an option contains card-specific anchors, pair with those so the policy
        # learns card interactions without an unnecessary cross-product against
        # every placement/count token. For non-card choices (yes/no, phase, zone
        # choices), the ordinary option anchors are the discriminating signal.
        selected = card_anchors or anchors
        for context in known_cards:
            for anchor in selected:
                out.append(f'x:{context}|{anchor}')
        return out

    def action_features(self, prompt, observation, action):
        state = self._state_features(observation)
        known = self._known_card_context(observation)
        kind = prompt['kind']; label = action.get('label', 'unknown')
        features = list(state)
        anchors = []
        card_anchors = []

        kind_label = f'kind_label:{kind}|{label}'
        features += [f'kind:{kind}', f'label:{label}', kind_label]
        anchors.append(kind_label)

        card = action.get('card')
        if card and 'code' in card:
            code = card['code']
            card_label = f'card_label:{code}|{label}'
            features += [f'card:{code}', card_label]
            anchors.append(card_label)
            card_anchors.append(card_label)
        elif card:
            rel = 'self' if card.get('controller') == observation['viewer'] else 'opp'
            slot = f'card_slot:{rel}|{card.get("location")}|{card.get("sequence")}|{label}'
            features.append(slot)
            anchors.append(slot)
            card_anchors.append(slot)

        if action.get('description') is not None:
            desc = action['description']
            desc_label = f'desc_label:{desc}|{label}'
            features += [f'desc:{desc}', desc_label]
            anchors.append(desc_label)
        if action.get('position') is not None:
            pos = f'position:{action["position"]}'
            features.append(pos)
            anchors.append(f'{pos}|{label}')

        features += self._conditioned_features(state, known, anchors, card_anchors)
        return tuple(features)

    def card_features(self, prompt, observation, card):
        state = self._state_features(observation)
        known = self._known_card_context(observation)
        kind = prompt['kind']
        features = list(state)
        kind_label = f'kind_label:{kind}|select_card'
        features += [f'kind:{kind}', 'label:select_card', kind_label]

        rel = 'self' if card.get('controller') == observation['viewer'] else 'opp'
        slot_anchor = f'candidate_slot:{rel}|{card.get("location")}|{card.get("sequence")}'
        features += [f'location:{card.get("location")}', f'controller_rel:{rel}', slot_anchor]
        anchors = [kind_label, slot_anchor]
        card_anchors = [slot_anchor]
        if 'code' in card:
            code = card['code']
            card_label = f'card_label:{code}|select_card'
            features += [f'card:{code}', card_label]
            anchors.append(card_label)
            card_anchors = [card_label]

        features += self._conditioned_features(state, known, anchors, card_anchors)
        return tuple(features)

    def complex_features(self, prompt, observation, option):
        """Features for a completely enumerated implicit legal response.

        ``option`` comes from legal_options.py and contains only safe data copied
        from the filtered prompt or from the player's selected response itself.
        Referee helper values used to prove legality never enter this function.
        """
        state = self._state_features(observation)
        known = self._known_card_context(observation)
        kind = prompt['kind']; label = option.get('label', 'complex')
        features = list(state)
        kind_label = f'kind_label:{kind}|{label}'
        features += [f'kind:{kind}', f'label:{label}', kind_label]
        anchors = [kind_label]
        card_anchors = []

        if option.get('selected_count') is not None:
            token = f'selected_count:{option["selected_count"]}'
            features.append(token)
            anchors.append(token)

        selected = option.get('selected_cards', ())
        for card in selected:
            rel = 'self' if card.get('controller') == observation['viewer'] else 'opp'
            slot = f'selected_slot:{rel}|{card.get("location")}|{card.get("sequence")}'
            features += [
                f'selected_location:{card.get("location")}',
                f'selected_controller_rel:{rel}',
                slot,
            ]
            anchors.append(slot)
            card_anchors.append(slot)
            if 'code' in card:
                code = card['code']
                card_token = f'card_label:{code}|{label}'
                features += [f'card:{code}', card_token]
                anchors.append(card_token)
                card_anchors[-1] = card_token

        ordered = option.get('ordered_cards', ())
        for position, card in enumerate(ordered):
            if 'code' in card:
                token = f'order:{position}|card:{card["code"]}'
                card_anchors.append(token)
            else:
                token = f'order:{position}|location:{card.get("location")}'
            features.append(token)
            anchors.append(token)

        for place in option.get('places', ()):
            if len(place) == 3:
                con, loc, seq = place
                rel = 'self' if con == observation['viewer'] else 'opp'
                token = f'place:{rel}|{loc}|{seq}'
                features.append(token)
                anchors.append(token)

        allocations = option.get('allocations')
        if allocations is not None:
            token = 'allocation:' + ','.join(str(int(v)) for v in allocations)
            features.append(token)
            anchors.append(token)
        if option.get('announced_mask') is not None:
            token = f'announced_mask:{int(option["announced_mask"])}'
            features.append(token)
            anchors.append(token)

        features += self._conditioned_features(state, known, anchors, card_anchors)
        return tuple(features)

    def score(self, features):
        return sum(self.weights.get(feature, 0.0) for feature in features)

    def probabilities(self, option_features):
        if not option_features: raise ValueError('empty policy option list')
        temperature = max(self.temperature, 1e-6)
        scores = [self.score(features) / temperature for features in option_features]
        high = max(scores)
        exps = [math.exp(max(-60.0, min(60.0, score - high))) for score in scores]
        total = sum(exps)
        return [value / total for value in exps]

    def sample(self, option_features):
        probs = self.probabilities(option_features)
        needle = self.rng.random(); acc = 0.0
        for index, probability in enumerate(probs):
            acc += probability
            if needle <= acc: return index
        return len(probs) - 1

    def update_episode(self, steps, winner, scale=None):
        """Symmetric terminal REINFORCE update from both players' perspectives."""
        if winner not in (0, 1): return
        if not steps: return
        if scale is None:
            scale = 1.0 / math.sqrt(len(steps))
        lr = self.learning_rate * scale
        for step in steps:
            reward = 1.0 if step.player == winner else -1.0
            probs = self.probabilities(step.option_features)
            for index, features in enumerate(step.option_features):
                coefficient = reward * ((1.0 if index == step.chosen else 0.0) - probs[index])
                delta = lr * coefficient
                if not delta: continue
                for feature in features:
                    self.weights[feature] = self.weights.get(feature, 0.0) + delta
        self.weights = {k: v for k, v in self.weights.items() if abs(v) >= 1e-12}

    def to_dict(self):
        return {
            'policy': 'sparse_softmax_reinforce_v3_contextual_actions',
            'seed': self.seed,
            'temperature': self.temperature,
            'learning_rate': self.learning_rate,
            'weights': dict(sorted(self.weights.items())),
        }

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + '\n')

    @classmethod
    def load(cls, path, seed=None):
        data = json.loads(Path(path).read_text())
        return cls(seed=data['seed'] if seed is None else seed,
                   temperature=data['temperature'], learning_rate=data['learning_rate'],
                   weights=data['weights'])

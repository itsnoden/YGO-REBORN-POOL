"""Minimal from-scratch self-play policy with sparse REINFORCE updates.

No card values, deck archetypes, tournament priors or human heuristics are baked
in. Features are derived only from information-safe observations and filtered
legal prompts. Card/action preferences can emerge only from simulated outcomes.

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
            f'lp_diff:{self._bucket(me["lp"] - them["lp"], 1000)}',
            f'hand_diff:{self._bucket(me["hand_count"] - them["hand_count"], 1)}',
            f'field_diff:{self._bucket(my_field - op_field, 1)}',
            f'grave_diff:{self._bucket(me["grave_count"] - them["grave_count"], 2)}',
        )

    def action_features(self, prompt, observation, action):
        state = self._state_features(observation)
        kind = prompt['kind']; label = action.get('label', 'unknown')
        features = list(state)
        features += [f'kind:{kind}', f'label:{label}', f'kind_label:{kind}|{label}']
        card = action.get('card')
        if card and 'code' in card:
            code = card['code']
            features += [f'card:{code}', f'card_label:{code}|{label}']
        if action.get('description') is not None:
            desc = action['description']
            features += [f'desc:{desc}', f'desc_label:{desc}|{label}']
        if action.get('position') is not None:
            features.append(f'position:{action["position"]}')
        return tuple(features)

    def card_features(self, prompt, observation, card):
        features = list(self._state_features(observation))
        features += [f'kind:{prompt["kind"]}', 'label:select_card',
                     f'kind_label:{prompt["kind"]}|select_card']
        if 'code' in card:
            features += [f'card:{card["code"]}', f'card_label:{card["code"]}|select_card']
        features += [f'location:{card.get("location")}', f'controller_rel:{"self" if card.get("controller") == observation["viewer"] else "opp"}']
        return tuple(features)

    def complex_features(self, prompt, observation, option):
        """Features for a completely enumerated implicit legal response.

        ``option`` comes from legal_options.py and contains only safe data copied
        from the filtered prompt or from the player's selected response itself.
        Referee helper values used to prove legality never enter this function.
        """
        state = self._state_features(observation)
        kind = prompt['kind']; label = option.get('label', 'complex')
        features = list(state)
        features += [f'kind:{kind}', f'label:{label}', f'kind_label:{kind}|{label}']
        if option.get('selected_count') is not None:
            features.append(f'selected_count:{option["selected_count"]}')

        selected = option.get('selected_cards', ())
        for card in selected:
            if 'code' in card:
                code = card['code']
                features += [f'card:{code}', f'card_label:{code}|{label}']
            features += [
                f'selected_location:{card.get("location")}',
                f'selected_controller_rel:{"self" if card.get("controller") == observation["viewer"] else "opp"}',
            ]

        ordered = option.get('ordered_cards', ())
        for position, card in enumerate(ordered):
            if 'code' in card:
                features.append(f'order:{position}|card:{card["code"]}')
            else:
                features.append(f'order:{position}|location:{card.get("location")}')

        for place in option.get('places', ()):
            if len(place) == 3:
                con, loc, seq = place
                rel = 'self' if con == observation['viewer'] else 'opp'
                features.append(f'place:{rel}|{loc}|{seq}')

        allocations = option.get('allocations')
        if allocations is not None:
            features.append('allocation:' + ','.join(str(int(v)) for v in allocations))
        if option.get('announced_mask') is not None:
            features.append(f'announced_mask:{int(option["announced_mask"])}')
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
            'policy': 'sparse_softmax_reinforce_v2_complex_actions',
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

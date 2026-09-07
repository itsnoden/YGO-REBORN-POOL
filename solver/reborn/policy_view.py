"""Final hidden-information boundary between ocgcore prompts and a pilot.

Raw decision messages are referee data. They can contain printed card codes even
when a player should only see an anonymous facedown card. A policy must consume
``policy_prompt_view`` plus ``observation_for`` output, never the raw Decision.
"""
from __future__ import annotations

from .effects import UnsupportedInteraction
from .observation import (
    LOCATION_DECK, LOCATION_HAND, LOCATION_MZONE, LOCATION_SZONE,
    LOCATION_GRAVE, LOCATION_REMOVED, LOCATION_EXTRA,
)


def _observed_entry(observation, card):
    if card.controller not in (0, 1): return None
    row = observation['players'][card.controller]
    seq = card.sequence
    if card.location == LOCATION_MZONE:
        slots = row['mzone']
        return slots[seq].get('card') if 0 <= seq < len(slots) and slots[seq].get('present') else None
    if card.location == LOCATION_SZONE:
        slots = row['szone']
        return slots[seq].get('card') if 0 <= seq < len(slots) and slots[seq].get('present') else None
    mapping = {
        LOCATION_HAND: 'hand', LOCATION_GRAVE: 'grave',
        LOCATION_REMOVED: 'removed', LOCATION_EXTRA: 'extra',
    }
    name = mapping.get(card.location)
    if name is None: return None
    values = row[name]
    return values[seq] if 0 <= seq < len(values) else None


def _filtered_card(card, observation):
    result = {
        'controller': card.controller,
        'location': card.location,
        'sequence': card.sequence,
    }
    if card.position is not None:
        result['position'] = card.position
    observed = _observed_entry(observation, card)
    if observed:
        for key in ('position', 'is_public', 'is_hidden'):
            if key in observed: result[key] = observed[key]
        if 'code' in observed:
            result['code'] = observed['code']
            return result

    viewer = observation['viewer']
    # A selection from the acting player's own Deck is itself a legal disclosure:
    # search/material prompts show the eligible cards to that player. Location 0
    # is used by core SelectCardCodes and is likewise an explicit prompt reveal.
    prompt_reveals_own_hidden = (
        card.controller == viewer and card.location in (0, LOCATION_DECK)
    )
    if prompt_reveals_own_hidden and not (observed and observed.get('is_hidden')):
        result['code'] = card.code
    return result


def policy_prompt_view(decision, observation):
    """Return the only prompt representation permitted for learned policies."""
    if observation.get('viewer') != decision.player:
        raise UnsupportedInteraction('prompt/observation player mismatch')
    view = {
        'kind': decision.kind,
        'player': decision.player,
        'minimum': decision.minimum,
        'maximum': decision.maximum,
        'cancelable': decision.cancelable,
        'actions': [],
        'cards': [_filtered_card(card, observation) for card in decision.cards],
        'meta': {},
    }
    safe_extra = {'index','currently_selected','direct_attackable','position','value'}
    for index, action in enumerate(decision.actions):
        row = {'choice_index': index, 'label': action.label}
        if action.card is not None:
            row['card'] = _filtered_card(action.card, observation)
        if action.description is not None: row['description'] = action.description
        if action.client_mode is not None: row['client_mode'] = action.client_mode
        for key, value in action.extra.items():
            if key in safe_extra: row[key] = value
        view['actions'].append(row)

    # Expose only information needed to understand a legal prompt. Referee-side
    # legality helper values (release values, sum params, opcode expressions) do
    # not belong in a learned policy input.
    meta = decision.meta
    if decision.kind == 'idle':
        for key in ('to_battle_phase','to_end_phase','can_shuffle_hand'):
            if key in meta: view['meta'][key] = meta[key]
    elif decision.kind == 'battle':
        for key in ('to_main_phase_2','to_end_phase'):
            if key in meta: view['meta'][key] = meta[key]
    elif decision.kind == 'chain':
        view['meta']['forced'] = bool(meta.get('forced', False))
    elif decision.kind in {'select_place','disable_field'}:
        view['meta']['places'] = list(meta.get('places', ()))
    elif decision.kind == 'counter':
        view['meta']['counter_type'] = meta.get('counter_type')
    elif decision.kind == 'select_sum':
        view['meta']['mode'] = meta.get('mode')
        view['meta']['accumulator'] = meta.get('accumulator')
    elif decision.kind in {'announce_race','announce_attribute'}:
        view['meta']['available'] = meta.get('available')
    elif decision.kind == 'announce_number':
        view['meta']['options'] = list(meta.get('options', ()))
    return view


def assert_no_hidden_code_leak(view, observation):
    """Regression assertion for opponent anonymous zones in policy inputs."""
    viewer = observation['viewer']
    cards = list(view.get('cards', ()))
    cards += [a['card'] for a in view.get('actions', ()) if 'card' in a]
    for card in cards:
        if card.get('controller') == viewer or 'code' not in card:
            continue
        observed = _observed_entry(observation, type('Ref', (), {
            'controller': card['controller'], 'location': card['location'],
            'sequence': card['sequence'],
        })())
        if not observed or 'code' not in observed:
            raise UnsupportedInteraction('policy prompt leaked opponent hidden card code')
    return True

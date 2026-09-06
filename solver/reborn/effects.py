"""Minimum typed effect contract. Descriptive IR is not executable certification."""
from dataclasses import dataclass,field
from enum import Enum


class UnsupportedInteraction(RuntimeError):pass


class EffectKind(str,Enum):
    ACTIVATED='activated'
    TRIGGER='trigger'
    CONTINUOUS='continuous'
    REPLACEMENT='replacement'
    PROCEDURE='procedure'
    WIN_CONDITION='win_condition'


@dataclass(frozen=True)
class EffectIR:
    card_id:str
    effect_id:str
    text_sha256:str
    kind:EffectKind
    activation_condition:dict
    cost:tuple
    targets:tuple
    resolution_condition:dict
    operations:tuple
    usage_limit:dict
    timing:dict
    required_capabilities:frozenset
    ruling_sources:tuple=()
    certified:bool=False


def require_supported(effect,current_text_hash,capabilities):
    if effect.text_sha256!=current_text_hash:
        raise UnsupportedInteraction('Official text changed; effect certificate invalid')
    if not effect.certified:
        raise UnsupportedInteraction('Uncertified effect')
    missing=effect.required_capabilities-set(capabilities)
    if missing:raise UnsupportedInteraction(f'Unsupported rules capabilities: {sorted(missing)}')


@dataclass
class UsageLedger:
    """Scope keys distinguish player/name and instance; reset by explicit turn."""
    used:set=field(default_factory=set)

    def claim(self,player,identity,effect_id,scope,turn):
        if scope not in ('turn','duel'):raise UnsupportedInteraction(scope)
        k=(player,identity,effect_id,scope,turn if scope=='turn' else None)
        if k in self.used:raise ValueError('Effect usage limit already consumed')
        self.used.add(k)


def certified_duel(*args,**kwargs):
    raise UnsupportedInteraction('Full duel engine not yet certified. Do not substitute proxy outcomes.')

"""Exploratory paired-seat matchup test for the saved blind Volcanic Prison deck.

This is deliberately NOT deck-ranking certification.  It uses the current
information-safe ChainContext pilot and pinned ocgcore infrastructure, but the
project's pilot-skill gate has not passed.  Results are stress-test samples only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from types import SimpleNamespace

from .chain_context_ab_eval import ChainContextPolicy
from .import_pool import ROOT, dump
from .payoff_matrix_eval import (
    run_frozen_policy_duel,
    train_universal_policy,
    usable_candidates,
)
from .search import validate


DECK_SPECS = {
    "Volcanic Prison": {
        "source": "saved_exact_blind_40",
        "cards": {
            "Volcanic Rocket": 3,
            "Volcanic Shell": 3,
            "Volcanic Scattershot": 3,
            "Breaker the Magical Warrior": 1,
            "Neo-Spacian Grand Mole": 1,
            "D.D. Warrior Lady": 1,
            "Sangan": 1,
            "Barrier Statue of the Inferno": 1,
            "D.D. Assailant": 1,
            "Blaze Accelerator": 3,
            "Back to Square One": 1,
            "Smashing Ground": 2,
            "Lightning Vortex": 1,
            "Heavy Storm": 1,
            "Giant Trunade": 1,
            "Mystical Space Typhoon": 1,
            "Book of Moon": 1,
            "Nobleman of Crossout": 1,
            "Royal Oppression": 3,
            "Mask of Restrict": 2,
            "Bottomless Trap Hole": 2,
            "Pulling the Rug": 1,
            "Phoenix Wing Wind Blast": 1,
            "Divine Wrath": 1,
            "Solemn Judgment": 1,
            "Torrential Tribute": 1,
            "Dust Tornado": 1,
        },
    },
    "DDT": {
        "source": "saved_exact_ratio_locked_40",
        "cards": {
            "Destiny HERO - Diamond Dude": 3,
            "Destiny HERO - Malicious": 3,
            "Card Trooper": 3,
            "Elemental HERO Stratos": 1,
            "Destiny HERO - Dasher": 1,
            "Dark Magician of Chaos": 1,
            "Destiny Draw": 3,
            "Reasoning": 3,
            "Monster Gate": 3,
            "Magical Stone Excavation": 3,
            "Upstart Goblin": 3,
            "Reinforcement of the Army": 2,
            "Machine Duplication": 2,
            "Brain Control": 1,
            "Dimension Fusion": 1,
            "Divine Sword - Phoenix Blade": 1,
            "Heavy Storm": 1,
            "Giant Trunade": 1,
            "Premature Burial": 1,
            "Card Destruction": 1,
            "Lightning Vortex": 1,
            "Return from the Different Dimension": 1,
        },
    },
    "Gravekeeper Royal Tribute v5": {
        "source": "saved_exact_current_40",
        "cards": {
            "Gravekeeper's Commandant": 3,
            "Gravekeeper's Spy": 3,
            "Gravekeeper's Assailant": 3,
            "Breaker the Magical Warrior": 1,
            "Neo-Spacian Grand Mole": 1,
            "D.D. Warrior Lady": 1,
            "Necrovalley": 3,
            "Royal Tribute": 3,
            "Terraforming": 3,
            "Upstart Goblin": 3,
            "Heavy Storm": 1,
            "Mystical Space Typhoon": 1,
            "Book of Moon": 1,
            "Nobleman of Crossout": 1,
            "Deck Devastation Virus": 1,
            "Anti-Spell Fragrance": 2,
            "Phoenix Wing Wind Blast": 1,
            "Dust Tornado": 1,
            "Bottomless Trap Hole": 2,
            "Royal Oppression": 1,
            "Solemn Judgment": 1,
            "Mirror Force": 1,
            "Torrential Tribute": 1,
            "Ring of Destruction": 1,
        },
    },
    "D-HERO Raiza Vanity": {
        "source": "saved_reference_40_for_perfect_circle_family",
        "cards": {
            "Raiza the Storm Monarch": 3,
            "Vanity's Fiend": 2,
            "Destiny HERO - Malicious": 3,
            "Destiny HERO - Disk Commander": 3,
            "Destiny HERO - Diamond Dude": 1,
            "Elemental HERO Stratos": 1,
            "Treeborn Frog": 1,
            "Card Trooper": 2,
            "Sangan": 1,
            "Spirit Reaper": 1,
            "Destiny Draw": 3,
            "Brain Control": 3,
            "Soul Exchange": 2,
            "Upstart Goblin": 3,
            "Reinforcement of the Army": 2,
            "Heavy Storm": 1,
            "Mystical Space Typhoon": 1,
            "Premature Burial": 1,
            "Book of Moon": 1,
            "Call of the Haunted": 1,
            "Crush Card Virus": 1,
            "Torrential Tribute": 1,
            "Mirror Force": 1,
            "Ring of Destruction": 1,
        },
    },
    "Macro Monarch": {
        "source": "saved_exact_max_win_rate_40",
        "cards": {
            "D.D. Survivor": 3,
            "D.D. Scout Plane": 1,
            "Banisher of the Radiance": 3,
            "Cyber Dragon": 3,
            "Raiza the Storm Monarch": 3,
            "Thestalos the Firestorm Monarch": 2,
            "Mobius the Frost Monarch": 1,
            "Dimensional Fissure": 3,
            "Brain Control": 3,
            "Enemy Controller": 3,
            "Soul Exchange": 1,
            "Upstart Goblin": 3,
            "Heavy Storm": 1,
            "Mystical Space Typhoon": 1,
            "Book of Moon": 1,
            "Macro Cosmos": 3,
            "Bottomless Trap Hole": 2,
            "Torrential Tribute": 1,
            "Mirror Force": 1,
            "Solemn Judgment": 1,
        },
    },
    "Ultimate Offering Gadget": {
        "source": "saved_exact_current_40",
        "cards": {
            "Green Gadget": 3,
            "Red Gadget": 3,
            "Yellow Gadget": 3,
            "Breaker the Magical Warrior": 1,
            "Neo-Spacian Grand Mole": 1,
            "D.D. Warrior Lady": 1,
            "Sangan": 1,
            "Mobius the Frost Monarch": 1,
            "Creature Swap": 2,
            "Smashing Ground": 3,
            "Nobleman of Crossout": 1,
            "Lightning Vortex": 1,
            "Limiter Removal": 1,
            "Heavy Storm": 1,
            "Mystical Space Typhoon": 1,
            "Book of Moon": 1,
            "Enemy Controller": 1,
            "Ultimate Offering": 3,
            "Royal Oppression": 3,
            "Bottomless Trap Hole": 2,
            "Torrential Tribute": 1,
            "Mirror Force": 1,
            "Dust Tornado": 1,
            "Compulsory Evacuation Device": 1,
            "Solemn Judgment": 1,
            "Phoenix Wing Wind Blast": 1,
        },
    },
    "Six Samurai": {
        "source": "ai_reconstructed_representative_40_no_double_summon",
        "cards": {
            "Grandmaster of the Six Samurai": 3,
            "Great Shogun Shien": 3,
            "The Six Samurai - Zanji": 3,
            "The Six Samurai - Irou": 3,
            "The Six Samurai - Yaichi": 3,
            "The Six Samurai - Kamon": 2,
            "Shien's Footsoldier": 2,
            "Reinforcement of the Army": 2,
            "Upstart Goblin": 3,
            "Smashing Ground": 2,
            "Cold Wave": 2,
            "Heavy Storm": 1,
            "Giant Trunade": 1,
            "Mystical Space Typhoon": 1,
            "Book of Moon": 1,
            "Bottomless Trap Hole": 2,
            "Torrential Tribute": 1,
            "Mirror Force": 1,
            "Solemn Judgment": 1,
            "Compulsory Evacuation Device": 1,
            "Dust Tornado": 1,
            "Return of the Six Samurai": 1,
        },
    },
    "Pure Brain-Control Monarch": {
        "source": "ai_reconstructed_representative_40",
        "cards": {
            "Raiza the Storm Monarch": 3,
            "Thestalos the Firestorm Monarch": 2,
            "Mobius the Frost Monarch": 1,
            "Cyber Dragon": 3,
            "Treeborn Frog": 1,
            "Sangan": 1,
            "Spirit Reaper": 1,
            "Breaker the Magical Warrior": 1,
            "D.D. Warrior Lady": 1,
            "Neo-Spacian Grand Mole": 1,
            "Gravekeeper's Spy": 2,
            "Brain Control": 3,
            "Soul Exchange": 2,
            "Enemy Controller": 3,
            "Reinforcement of the Army": 2,
            "Heavy Storm": 1,
            "Mystical Space Typhoon": 1,
            "Book of Moon": 1,
            "Nobleman of Crossout": 1,
            "Smashing Ground": 2,
            "Bottomless Trap Hole": 2,
            "Torrential Tribute": 1,
            "Mirror Force": 1,
            "Solemn Judgment": 1,
            "Call of the Haunted": 1,
            "Compulsory Evacuation Device": 1,
        },
    },
    "Demise Doom Dozer": {
        "source": "ai_reconstructed_representative_40_no_advanced_ritual_art",
        "cards": {
            "Demise, King of Armageddon": 3,
            "Doom Dozer": 3,
            "Senju of the Thousand Hands": 3,
            "Sonic Bird": 3,
            "Insect Knight": 3,
            "Neo Bug": 3,
            "End of the World": 3,
            "Upstart Goblin": 3,
            "Megamorph": 2,
            "Smashing Ground": 2,
            "Heavy Storm": 1,
            "Giant Trunade": 1,
            "Mystical Space Typhoon": 1,
            "Book of Moon": 1,
            "Brain Control": 1,
            "Premature Burial": 1,
            "Lightning Vortex": 1,
            "Bottomless Trap Hole": 2,
            "Torrential Tribute": 1,
            "Mirror Force": 1,
            "Solemn Judgment": 1,
        },
    },
}


def build_name_index(cards):
    index = {}
    for cid, card in cards.items():
        index.setdefault(card["name"].casefold(), []).append(cid)
    return index


def resolve_deck(spec, cards, mapped):
    by_name = build_name_index(cards)
    deck = []
    unresolved = []
    unmapped = []
    ambiguous = []
    for name, count in spec["cards"].items():
        matches = by_name.get(name.casefold(), [])
        if not matches:
            unresolved.append(name)
            continue
        if len(matches) != 1:
            ambiguous.append({"name": name, "ids": matches})
            continue
        cid = matches[0]
        if cid not in mapped:
            unmapped.append({"name": name, "id": cid})
            continue
        deck.extend([cid] * count)
    if unresolved or unmapped or ambiguous:
        return None, {
            "unresolved_names": unresolved,
            "unmapped_cards": unmapped,
            "ambiguous_names": ambiguous,
            "requested_count": sum(spec["cards"].values()),
            "resolved_count": len(deck),
        }
    validate(deck, cards)
    return deck, {
        "requested_count": sum(spec["cards"].values()),
        "resolved_count": len(deck),
    }


def summarize_rows(rows):
    completed = [r for r in rows if r.get("completed")]
    wins = sum(r.get("volcanic_result") == "win" for r in completed)
    losses = sum(r.get("volcanic_result") == "loss" for r in completed)
    draws = sum(r.get("volcanic_result") == "draw" for r in completed)
    fallbacks = sum(int(r.get("fallback_decisions", 0)) for r in rows)
    blockers = [r.get("blocker") for r in rows if not r.get("completed")]
    return {
        "games": len(rows),
        "completed": len(completed),
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "score_rate": ((wins + 0.5 * draws) / len(completed)) if completed else None,
        "fallback_decisions": fallbacks,
        "blocked": len(rows) - len(completed),
        "blockers": blockers,
        "clean_engine_sample": bool(rows) and len(completed) == len(rows) and fallbacks == 0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--library", required=True)
    p.add_argument("--database", required=True)
    p.add_argument("--scripts", required=True)
    p.add_argument("--train-games", type=int, default=64)
    p.add_argument("--train-decks", type=int, default=8)
    p.add_argument("--seeds-per-matchup", type=int, default=4)
    p.add_argument("--budget", type=int, default=5000)
    p.add_argument("--train-seed", type=int, default=351000)
    p.add_argument("--eval-seed", type=int, default=361000)
    p.add_argument("--policy-seed", type=int, default=20260913)
    a = p.parse_args()

    cards = {c["id"]: c for c in json.loads((ROOT/"data/processed/cards.json").read_text())}
    mapped = {
        r["reborn_id"]: r
        for r in json.loads((ROOT/"data/processed/engine_cards.json").read_text())
    }

    resolved = {}
    deck_checks = {}
    for name, spec in DECK_SPECS.items():
        deck, check = resolve_deck(spec, cards, mapped)
        check["source"] = spec["source"]
        deck_checks[name] = check
        if deck is not None:
            resolved[name] = deck

    volcanic = resolved.get("Volcanic Prison")
    if volcanic is None:
        dump(ROOT/"reports/volcanic_meta_sim.json", {
            "status": "blocked",
            "reason": "Volcanic Prison did not fully resolve to mapped engine cards",
            "deck_checks": deck_checks,
        })
        raise SystemExit("Volcanic Prison did not resolve")

    usable = usable_candidates(cards, mapped)
    if len(usable) < a.train_decks:
        raise RuntimeError(f"need {a.train_decks} training candidates; found {len(usable)}")

    train_args = SimpleNamespace(
        library=a.library,
        database=a.database,
        scripts=a.scripts,
        train_games=a.train_games,
        train_seed=a.train_seed,
        policy_seed=a.policy_seed,
        budget=a.budget,
    )
    policy, training_rows, training_complete = train_universal_policy(
        train_args, mapped, usable[:a.train_decks], ChainContextPolicy
    )

    matchups = {}
    all_rows = []
    if training_complete:
        opp_names = [name for name in DECK_SPECS if name != "Volcanic Prison"]
        for opp_index, opp_name in enumerate(opp_names):
            if opp_name not in resolved:
                matchups[opp_name] = {
                    "status": "not_run_deck_unresolved",
                    "deck_check": deck_checks[opp_name],
                }
                continue
            opp = resolved[opp_name]
            rows = []
            for pair in range(a.seeds_per_matchup):
                seed = a.eval_seed + opp_index * 100 + pair

                first = run_frozen_policy_duel(
                    a.library, a.database, a.scripts,
                    (volcanic, opp), mapped, policy, seed, a.budget
                )
                first = dict(first)
                winner = first.get("winner")
                first["volcanic_seat"] = 0
                first["volcanic_position"] = "first"
                first["volcanic_result"] = (
                    "win" if winner == 0 else
                    "loss" if winner == 1 else
                    "draw" if first.get("completed") else None
                )

                second = run_frozen_policy_duel(
                    a.library, a.database, a.scripts,
                    (opp, volcanic), mapped, policy, seed, a.budget
                )
                second = dict(second)
                winner = second.get("winner")
                second["volcanic_seat"] = 1
                second["volcanic_position"] = "second"
                second["volcanic_result"] = (
                    "win" if winner == 1 else
                    "loss" if winner == 0 else
                    "draw" if second.get("completed") else None
                )

                rows.extend([first, second])
                all_rows.extend([
                    {"opponent": opp_name, **first},
                    {"opponent": opp_name, **second},
                ])

            first_rows = [r for r in rows if r["volcanic_position"] == "first"]
            second_rows = [r for r in rows if r["volcanic_position"] == "second"]
            matchups[opp_name] = {
                "status": "completed" if all(r.get("completed") for r in rows) else "partial",
                "opponent_source": DECK_SPECS[opp_name]["source"],
                "volcanic_first": summarize_rows(first_rows),
                "volcanic_second": summarize_rows(second_rows),
                "combined": summarize_rows(rows),
                "rows": rows,
            }

    report = {
        "status": "completed" if training_complete else "blocked_training",
        "purpose": "exploratory_named_meta_paired_seat_stress_test",
        "profile": "reborn",
        "external_strategy_priors": False,
        "pilot_model": "chain_context",
        "pilot_skill_certified_for_ranking": False,
        "deck_ranking_evidence": False,
        "exploratory_only": True,
        "training_games_requested": a.train_games,
        "training_games_completed": sum(bool(r.get("completed")) for r in training_rows),
        "training_complete": training_complete,
        "seeds_per_matchup": a.seeds_per_matchup,
        "duels_per_resolved_matchup": a.seeds_per_matchup * 2,
        "deck_checks": deck_checks,
        "matchups": matchups,
        "all_duels": all_rows,
        "note": (
            "These are actual ocgcore paired-seat duel samples under the current "
            "zero-human-prior ChainContext pilot. The pilot has NOT passed the project's "
            "deck-strength qualification gate, so raw score rates are exploratory stress "
            "signals, not true matchup win-rate estimates."
        ),
    }
    dump(ROOT/"reports/volcanic_meta_sim.json", report)

    compact = {
        name: {
            "source": data.get("opponent_source"),
            "status": data.get("status"),
            "first": data.get("volcanic_first"),
            "second": data.get("volcanic_second"),
            "combined": data.get("combined"),
        }
        for name, data in matchups.items()
    }
    print(json.dumps({
        "training_complete": training_complete,
        "training_completed": report["training_games_completed"],
        "matchups": compact,
        "deck_checks": deck_checks,
        "pilot_skill_certified_for_ranking": False,
    }, indent=2))

    if not training_complete:
        raise SystemExit("pilot training did not complete")


if __name__ == "__main__":
    main()

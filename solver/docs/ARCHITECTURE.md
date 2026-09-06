# Architecture and accuracy contract

Implementation update: use the existing EDOPro core and pinned Project Ignis
effects for steps 3–4. The local EffectIR remains an audit/capability contract;
it is not a replacement rules engine. See ENGINE.md for actual coverage.

1. **Immutable inputs:** hash the exact MASTER, BANLIST and findings snapshots.
   Parse only the confirmed membership section; reject duplicate names, gaps or
   wrong counts. Retain banlist entries absent from the pool as audit findings,
   never silently add them. Default unlisted cards to 3 by the saved banlist rule.
2. **Current official text:** exact title matching, official card IDs, type,
   attributes, full effect text, timestamps and hashes. Missing matches remain
   queued. Do not fuzzy-match without an explicit reviewed alias record.
3. **Effect IR:** separate activation legality, cost, target selection, resolution
   checks, operations, replacement effects, continuous modifiers, trigger timing,
   optionality and use/activation limits. Every IR references a text hash and
   verified ruling sources. Text pattern tags are a separate non-executable layer.
4. **Rules kernel:** card instances versus names, owner versus controller, zones,
   public/private views, phase/step, player priority, chain windows, spell speeds,
   cost commitment, LIFO resolution, trigger queues, simultaneous events,
   last-known information, missing timing, summon procedures/restrictions,
   damage-step substeps, replacement ordering, negation, target legality at
   activation/resolution, reset scopes, deck-out and alternate wins. Capabilities
   are explicit. Never treat an unsupported event as pass or no-op.
5. **Interaction mining:** scan every legal card. Directed producer/consumer
   hypotheses, named-card references, bounded symbolic resource exploration,
   strongly connected components, FTK/OTK/lock/hand-loop/recovery categories.
   A cycle is only a hypothesis until legal state/action replay establishes it.
   Unlimited resource transitions are not proof of legal infinite loops.
6. **Deck search:** exact 40-card capacity, Main Deck only, copy limits; graph-seed
   beam search, uniform random restarts, one/two-slot mutation, genetic crossover.
   Maintain diversity and mandatory full-pool exposure rather than prefiltering
   on reputation. Surrogate scores prioritize testing only, never rank strength.
7. **Piloting:** information-set search with legal public observations, sampled
   hidden states, distinct training/evaluation seeds and compute budgets. Never
   reveal opponent hands or future draws. Increase planning budgets on complex
   candidates and measure convergence; evaluate both seats with paired seeds.
8. **Double oracle:** create empirical payoff matrices from certified games,
   solve restricted population game, then optimize best responses against the
   mixture and separately attack each incumbent. Add counterdecks and repeat.
   Report pure-deck worst opponent lower bound as the maximin deck objective;
   mixture equilibrium is an adversary training device, not a 40-card answer.
9. **Finalists:** independent seeds, confidence intervals, first/second split,
   timeouts/unsupported games separately, card-by-card ablation and replacement,
   opposing pilot budget sensitivity and entire archived adversary population.
10. **Persistence:** commit source hashes, effect versions, rules profile,
    RNG seeds, deck multisets, pilots, trajectories, payoff matrices, checkpoints,
    unresolved rulings and invalidated findings. Resume from latest commit.

## Format decisions still to verify

Latest card errata is settled by user instruction. Reborn turn-one draw,
priority convention, field-spell coexistence and Extra Deck capacity are NOT
implied by card errata. Select and verify a rules profile before certified duels.
Modern TCG can be a separately labelled experimental profile, never silently
claimed as a confirmed Reborn behavior.

## Metrics

Win = terminal rule result, draw = explicit rule result; budget exhaustion is
unresolved, not a draw. FTK = victory on the first player's first turn before
opponent's first turn; OTK definition must identify whose turn and starting LP.
Consistency/brick rate require a versioned functional-success definition, not
merely monsterless hands. Recovery uses documented disruption interventions and
paired seeds. Card advantage tracks hand/board changes plus accessible resources
separately, never one unqualified count. All denominators and unsupported counts
are reported. Optimization and held-out evaluation never reuse random seeds.

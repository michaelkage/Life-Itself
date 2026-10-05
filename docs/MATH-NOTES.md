# Math Notes

Corrections to the equations in the original design brief, with the derivations.
Every change here is enforced by a test in `tests/test_simulation.py` — if a fix
gets reverted, a test fails.

---

## 1. The decay constant could go negative

**Specified:**

```
R   = R_0 * e^(-lambda * t)
lam = lambda_base * (Mod_Age + Mod_Visibility - Mod_Trauma)
```

`Mod_Trauma` is *subtracted*, so a large trauma value drives λ negative. Cheapest
collision in the spec's own table — petty theft (2.0), young adult (1.0), noon and
clear (0.8):

```
lam = 0.01 * (1.0 + 0.8 - 2.0) = -0.002
```

Negative λ makes `e^(-lam*t)` **increase**, so the petty-theft memory gets
*stronger* the longer it goes unmentioned. It never fades at all.

The same line breaks the armed-assault case from the other side: the surviving
`Mod_Age + Mod_Visibility` term makes the "permanent" memory decay 1.75× faster
than baseline.

**Fixed** — every factor becomes a multiplier:

```
lam = lambda_base * Mod_Age * Mod_Visibility * DecayRate
```

Multiplication cannot produce a negative rate as long as no factor is negative,
so the bug is unrepresentable rather than guarded against.

This preserves the intended ordering exactly, because the Trauma column was
already *inverse*: armed assault was given the small value 0.05 precisely because
small means "never fades". It has been renamed `DECAY_RATE_MULTIPLIER` so the
direction is obvious at every call site — under the original name, `2.0` for petty
theft reads as "twice as traumatic" when it actually means "twice as forgettable".

---

## 2. Permanent memories are impossible with a bare exponential

**Specified:** armed assault has λ ≈ 0 and should "lock permanently into the
database, never fully decaying".

Any λ > 0 reaches zero eventually. At the spec's own numbers, λ = 0.0032/hr erases
a shooting in about a year. Setting λ = 0 outright would make it *exactly* as
permanent for armed assault as for a polite greeting — the modifier stops
discriminating.

**Fixed** — fade toward a permanent scar rather than toward nothing:

```
R(t) = R_0 * (floor + (1 - floor) * e^(-lambda * t))
```

| Action | Floor | Effect |
| --- | --- | --- |
| Polite interaction | 0.0 | forgotten entirely |
| Vandalism | 0.0 | forgotten entirely |
| Petty theft | 0.0 | forgotten entirely |
| Assault | 0.4 | scar, eventually too faint to name anyone |
| **Armed assault** | **0.85** | still nameable years later |

Scaling by `R_0` instead of adding a constant matters: a *faint* memory of a
violent act must not inherit permanence from its tag, or a half-remembered
glimpse would convict more durably than a clear one.

Petty theft deliberately gets **no** floor. The brief grants permanence only to
the violent cases, and a small floor on theft would leave every shoplifting rumour
alive forever, filling the city with stale whispers.

---

## 3. Decay rate — measured, not guessed

Transmission re-bases the listener's `initial_impact` to the speaker's *current*
retention. Every hop therefore compounds the previous hop's decay and a chain dies
superlinearly. That compounding — not the base rate — is what makes the telephone
effect work.

Measured over a 16-NPC chain, 2 in-game hours per hop, ADULT witness, theft:

| `lambda_base` | last hop still named | last hop still alive |
| --- | --- | --- |
| 0.08 | 1 | 4 |
| 0.04 | 2 | 7 |
| **0.02** | **3** | **10** |
| 0.01 | 4 | 14 |

`0.02` is the pick. The name stays exact for ~3 hops, so actual witnesses can
still accuse accurately, and the degraded description survives ~10 hops — far
enough to reach another district and send a patrol after the wrong person.

The brief's implied 0.01 is not as inert as it first appears, because the
compounding does the work. At 0.01 a rumour keeps its name for 4 hops and lives
14, which is close enough that the morph still happens but the failure mode
becomes rare — most crimes never misdirect anyone.

---

## 4. The desperation index and the moral shackle were on different scales

**Specified:**

```
DI = (Overpopulation * 1.2) + (SupplyShortage * 1.5)
   + (Weather * 0.8) + (Corruption * 1.1)
```

The weights sum to **4.60**, so with stresses normalised to 0–1, DI ranges
0.00–4.60. `MoralShackle` was documented as **0.20–0.95**. The comparison
`DI > MoralShackle` was therefore across a five-fold scale mismatch:

| Uniform stress | DI | 0.20 shackle | 0.95 shackle |
| --- | --- | --- | --- |
| 0.1 | 0.46 | breaks | holds |
| 0.2 | 0.92 | breaks | holds |
| 0.3 | 1.38 | breaks | **breaks** |

Moderate pressure criminalised the entire city on day one, and the two ends of
the shackle range were indistinguishable — the "career criminal" at 0.20 and the
"fiercely honest citizen" at 0.95 flipped under the same conditions.

**Fixed** — divide by the weight sum so DI is 0–1 and directly comparable:

```
DI = sum(stress_k * w_k) / sum(w_k)
```

Relative importance is preserved exactly: supply shortage still bites hardest,
weather still least. Now 0.3 uniform stress yields DI = 0.30 and breaks nobody,
while 0.75 stress breaks the 0.20 criminal and spares the 0.95 paragon.

---

## 5. `DescriptionDelta` cannot be a `FVector`

A `FVector` of (Height, Clothing Color, Masked) cannot represent a rumour,
because a rumour is formed by **merging** what several NPCs remember. Two
witnesses who each saw "about 1.8m" do not average into a sharper 1.8m — they
average into a *wider* spread of guesses about the truth.

Each trait now carries its own uncertainty, and hearing the same rumour twice
narrows it. A rumour heard once stays vague; one corroborated three times
sharpens into a usable description.

**Height.** `height_uncertainty_m` is the error of the *mean* of all contributing
witnesses, so merging is `sqrt(sum(sigma_i^2 * n_i^2)) / n_total`. The naive
quadrature sum `sqrt(sigma_1^2 + sigma_2^2)` is wrong in the intuitive direction —
it **widens** uncertainty on corroboration, actively punishing the behaviour the
design wants to reward.

**Masked.** Stored as certainty in the decision rather than P(masked), combined
with an agreement-aware operator: agreement compounds toward certainty
(`c + (1-c)*c_other`), contradiction collapses it (`c * (1-c_other)`). Averaging
is the obvious choice and it is inert — pooling two estimates of 0.6 returns 0.6,
so two witnesses who both clearly saw a masked face would leave the rumour exactly
as unsure as one witness did.

---

## 6. Two consequences worth knowing about

**Older witnesses produce shorter-reaching rumours.** The Age multiplier compounds
across every hop, so the same crime witnessed by a senior citizen travels
materially less far than one witnessed by a young adult — far enough that it can
die before reaching a patrol. Crimes with elderly witnesses go effectively
unreported. This falls out of the model rather than being designed, so it is
pinned by a test (`test_older_witness_produces_a_shorter_reach`) to keep it from
being rediscovered later as an unexplained bug.

**Transmission has two floors, not one.** Naming a person in a crime is an
accusation and needs real evidence (`0.05`); passing on "someone tall in a dark
jacket" is idle talk that costs the teller nothing (`0.01`). Using a single
cutoff silently kills a rumour at the exact moment it stops naming the player,
which is backwards — the appearance-only phase is precisely what sends police
after the wrong person.

---

# Part two: the systems that were specified but not built

Sections 1-6 covered systems that existed and were wrong. The rest of the brief
defined mechanics in prose with equations or thresholds attached, and those had
never been built at all. They turned out to contain six more bugs of the same
kind: values that were self-consistent on paper and broke the moment they ran.

## 7. Trauma tiers conflate two independent axes

Brief 4.A lists each tier with a comma and a slash:

```
Level 1 Anxious    -- witnessed petty crime     / rising shortages
Level 2 Paranoid   -- direct victim of theft    / high district hunger
Level 3 Vigilante  -- total systemic collapse   / zero law presence
```

Read as a flat list of alternatives, and one event reaches the top tier. A
witness to a single armed assault carries `InitialImpact` 1.0, so a linear
impact-to-tier mapping puts them at Level 3 immediately — "zero law presence",
a condition one crime cannot create. Whether the notation means *or* or *and* is
genuinely ambiguous in the brief.

Resolved by splitting the axes, which are independent in the fiction:

| Axis | Question | Decay |
|---|---|---|
| `personal_stress` | what was done **to** this person | half-life ~23 days |
| `desperation_index` | what is happening **around** them | district dynamics |

Levels 1-2 come from whichever axis is worse. The asymmetry that matters:

- `personal_level` caps at **Paranoid**. No amount of personal trauma reaches
  Level 3 on its own. This is the fix.
- The environment axis has no cap, and should not. Level 3's behaviour — "forms
  or joins localized protection rings, refuses to talk to law enforcement" — is
  largely *civic*. A citizen in a lawless district who was never victimised
  absolutely does join a protection ring. Demanding both axes was
  over-correcting the brief's ambiguity in the other direction.

Recovery is multiplicative, not a reset: `stress *= 0.97^days`. The brief calls
Level 2 "semi-permanent", so a victim does not forget being robbed — they stop
being defined by it.

Pinned by `test_one_armed_assault_cannot_make_a_vigilante`,
`test_environment_alone_makes_a_vigilante`.

## 8. The DI inputs had no dynamics, so the city was frozen

Brief 1.C says every citizen computes DI "on their daily cycle". No growth, decay,
or reversion rate is given for any input. A district is therefore static: the
daily cycle recomputes an identical number forever.

Nothing can deteriorate. And brief 2.B's city scars — which trigger on *sustained*
critical DI — could never fire against a city that never changes. The system had
a daily tick driving a constant.

Fixed by giving each input a rate, in one of two shapes:

| Input | Shape | Why |
|---|---|---|
| overpopulation | mean-reverting | derived from population/capacity; people move districts over weeks |
| supply shortage | mean-reverting, high persistence | weather-driven scarcity persists because the shelves are already empty |
| corruption | **asymmetric** | rises at `0.12`, falls at `0.01` |
| weather | mean-reverting | external, supplied per-day |

The corruption asymmetry is the load-bearing one. Corruption that decayed as
readily as it grew would mean any district could be cleaned up by arresting the
right people, which deletes the structural premise of the setting.

**Calibration.** The first pass used `CORRUPTION_PRESSURE = 0.35`, and the
equilibrium plateaued below both thresholds:

```
weather 1.0, 4x overpopulation, no policing:
    DI = 0.935   below the 0.95 paragon moral shackle, permanently
    corruption equilibrated near 0.73
```

So the top of the moral range was unreachable — a fiercely honest citizen never
breaks, in any city, however far gone — and the achievable DI range was
narrower than the model claimed. Raising pressure to `0.8` fixed the range:

| Sustained weather | Equilibrium DI | Outcome |
|---|---|---|
| 0.0 | 0.78 | corrupt, but no scars — scarcity alone does not ruin a district |
| 0.2 | 0.83 | no scars |
| 0.6 | 0.93 | scars |
| 1.0 | 1.00 | scars, and even the paragon breaks |

The clear-weather row is the point, and is pinned by
`test_scarcity_alone_does_not_scar_a_district`. A district has to be ruined by
something compounding, or the threshold means nothing.

## 9. City scars flickered

Brief 2.B: "if the DI of a district stays critical for more than three in-game
days". No definition of critical, and no way back. A strict `>` test on a
district hovering near the mark flips the whole city between clean and ruined on
alternate days.

Measured on a plausible series — `[0.90, 0.80, 0.88, 0.82, 0.91, 0.79, 0.86, 0.84]`
against a threshold of 0.85 — the strict count is 4 of 8 days, which *does* meet
the threshold. But six of eight days are ≥ 0.79. The district is plainly
collapsing and a one-day dip to 0.79 resets the entire counter. Every material
swap, audio sub-mix, and police posture would strobe with it.

Fixed with hysteresis — two thresholds, not one:

| Constant | Value | Role |
|---|---|---|
| `SCAR_ENTER_DI` | 0.85 | entering above this starts the countdown |
| `SCAR_EXIT_DI` | 0.60 | must stay below this to recover |
| `SCAR_DAYS_REQUIRED` | 3 | consecutive days above enter |
| `SCAR_RECOVERY_DAYS` | 4 | consecutive days below exit |

The 0.25-wide band between them holds whatever state the district was already
in. Pinned by `test_hysteresis_prevents_flicker`.

## 10. An arrest could outrun its evidence

Information reaches police through the gossip network. A rumour below
`TELEPHONE_THRESHOLD = 0.6` has already lost the target's identity — the brief's
own `police_response` handles this correctly and produces a *stop*, not a pursuit.

But brief 2.A then proceeds from the stop as though stop and arrest were the
same thing. The player's file accumulates real charges against a predicate fact
that names nobody. A file with no provable act cannot carry a
tried-corruption charge, a plea bargain, or a trial — yet it accumulated all
three.

Fixed by separating the two things the brief runs together:

| Outcome | Precondition |
|---|---|
| `None` | corruption suppressed the response |
| `Stop` | a patrol acted, no provable charge on the file |
| `Arrest` | a patrol acted **and** a provable charge exists |

Unwitnessed reports are still *filed* — an unresolved report is intelligence about
the player, and the file should know about it. They just are not `provable`.

Two sub-bugs fell out of this:

- **Corroboration scored the wrong variable.** A lone witness with retention
  above 0.9 was promoted to `corroborated`, so two agreeing witnesses and one
  confident witness produced identical files. Corroboration means there is a
  *second witness*, which the single-memory function cannot see. Promotion now
  happens only in `file_from_memories`, where witness count is visible.
- **Two witnesses to one act became two charges**, double-counting a single
  incident. Corroboration now strengthens one charge rather than stacking.

Pinned by `test_faded_memory_cannot_become_a_charge`,
`test_corroboration_strengthens_rather_than_stacks`.

## 11. Corruption stacked until the legal system vanished

Brief 2.B: corrupt districts "ignore minor offenses unless directly targeted by a
bribe". Taken as a multiplier and applied uniformly:

```
corruption 0.9 -> petty theft enforced 0.10
               -> arrest odds 0.10 as well
               -> chance of any arrest 0.01%
```

The city silently stopped having a legal system. One district's character trait
cascaded into a global property of the game.

Fixed by confining corruption to where the brief puts it — *minor* offences —
with a hard floor:

```python
if severity >= MINOR_OFFENCE_CUTOFF:      # 0.45
    return max(1.0 - 0.1 * corruption, ENFORCEMENT_FLOOR)
return max(1.0 - corruption, ENFORCEMENT_FLOOR)
```

Police in a ruined district stop caring about shoplifting. They do not stop
caring about a shooting. `ENFORCEMENT_FLOOR = 0.12` guarantees an offence class
can always be prosecuted.

One exception, and it is absolute: the attempted-bribery charge is never softened
by district corruption. An officer who can be bought is precisely why bribing one
cannot work, so this is the one charge that corruption does not touch.

Pinned by `test_serious_violence_stays_prosecutable`,
`test_bribe_charge_survives_a_pacified_district`.

## 12. Fixer betrayal was strictly dominant

Brief 4.B: a desperate fixer "might take your bribe money and instantly file an
anonymous tip to clear their own standing warrants". Compare the fixer's two
outcomes:

| | Bribe | Warrants cleared | Player removed as witness | Cost |
|---|---|---|---|---|
| Loyal | kept | no | no | none |
| Betray | kept | **yes** | **yes** | **none** |

Nothing is lost by betraying. No exposure risk, no reputational damage among
peers, no chance of being caught — the brief attaches none. Under those payoffs a
rational fixer betrays **every time**, so "might betray" would arrive as
guaranteed scripted ambushes, and the player would correctly conclude fixers are
not a route at all.

Fixed by giving betrayal something to lose:

```
p_betray = clamp01(desperation × greed(bribe, warrants) − 0.55 × standing)
greed    = 0.45×bribe / (0.45×bribe + warrants)
```

- `desperation` is the brief's own trigger — peak pressure does raise the odds.
- `greed` saturates toward 1 with bribe size and *shrinks* if the fixer has
  little to gain. A cheap fixer with clean books has no reason to squeal.
- `standing` is the counterweight the brief never supplied. A well-connected fixer
  risks everything by squealing, and knows it.

Measured: peak desperation with mid standing gives `p ≈ 0.14`; the same fixer at
standing 0.9 gives `p ≈ 0.0`; an unknown fixer with deep warrants at standing
0.2 gives `p ≈ 0.24`. Somewhere between certain and never, which is where the
mechanic is interesting.

**Atomicity.** `negotiate` returns a single `Negotiation`, never two calls.
Splitting "did they take the money" from "did they squeal" would let a caller
observe the payment and skip the betrayal — the one thing this mechanic must not
allow. Pinned by `test_betrayal_always_takes_the_money`.

---

# Bugs found while building, not in the design

These are implementation faults, not design faults. Recorded because the first two
are the kind that make a tuning sweep silently return nothing.

## 13. The tuning knob was welded shut

```python
def decay_constant(..., lambda_base: float = LAMBDA_BASE) -> float:
```

Python binds default arguments at *definition* time. Rebinding `decay.LAMBDA_BASE`
at runtime — the obvious way to tune — changed the module constant and did
nothing to the function. The first sweep returned an identical curve for every
rate from 0.01 to 0.08, which is what exposed it.

Fixed to `float | None = None`, resolved inside the body. Every tuning parameter
in the project defaults to `None` for this reason, and the C++ port must resolve
them at runtime too — binding at link time reproduces the same fault.

## 14. A reordered field silently captured the wrong argument

`Description.observations` was inserted as the third field of a dataclass with
defaults after it:

```python
Description(1.82, 0.3, {"black": 0.8}, False, 0.9)
#                                    ^^^ colour dict landed in `observations`
#                                         and `False` landed in jacket_colour_weights
```

No exception. No warning. The description was silently corrupt. `observations` is
now the **last** field by design, and
`test_positional_construction_still_maps_to_the_right_fields` pins it. C++
aggregate initialisation turns this into a compile error, which is the one place
the port is strictly safer than the prototype.
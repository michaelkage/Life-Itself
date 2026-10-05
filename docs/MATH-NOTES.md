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
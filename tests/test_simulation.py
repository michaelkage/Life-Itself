"""Test suite for the simulation core.

Deliberately no pytest dependency -- `python -m unittest` on a bare interpreter is
the only requirement, matching the engine's C++ target of no external libraries.
"""

import unittest

from simreality import (
    ActionTag,
    AgeBand,
    Description,
    District,
    NPC,
    NPCMemory,
    Weather,
    decay,
    decay_constant,
    desperation_index,
    evaluate,
    police_response,
    retention_after,
    retell,
    converse,
    TELEPHONE_THRESHOLD,
)


def make_memory(
    witness="w1",
    target="player-402",
    impact=1.0,
    retention=1.0,
    hour=12.0,
    tag=ActionTag.CRIME_THEFT,
    description=None,
):
    return NPCMemory(
        witness_id=witness,
        target_entity_id=target,
        initial_impact=impact,
        retention=retention,
        timestamp_hour=hour,
        action_tag=tag,
        description=description
        or Description(
            height_m=1.82,
            height_uncertainty_m=0.3,
            jacket_colour_weights={"black": 0.8},
            masked=False,
            masked_confidence=0.9,
        ),
    )


class TestDecayEquation(unittest.TestCase):
    def test_lambda_is_never_negative(self):
        """The spec's subtractive form drove lambda negative for petty theft.

        Verify the corrected product form holds for every combination of the
        modifier tables -- cheap theft, bad light, old witness is the worst case.
        """
        for age in AgeBand:
            for tag in ActionTag:
                for hour in (0.0, 12.0, 23.9):
                    for weather in Weather:
                        lam = decay_constant(age, tag, hour, weather)
                        self.assertGreaterEqual(
                            lam, 0.0, f"negative lambda: {age} {tag} {hour} {weather}"
                        )

    def test_retention_never_increases_with_time(self):
        """Regression: negative lambda made memories strengthen as they aged."""
        for tag in ActionTag:
            memory = make_memory(tag=tag)
            previous = 2.0
            for hour in [12.0 + i for i in range(0, 400, 4)]:
                current = retention_after(
                    memory, AgeBand.YOUNG_ADULT, hour, Weather.CLEAR
                )
                self.assertLessEqual(current, previous + 1e-9, f"{tag} rose at hour {hour}")
                previous = current

    def test_armed_assault_never_fully_decays(self):
        """Spec intent: witnessed armed assault locks into the database.

        Settles at RETENTION_FLOOR = 0.85 rather than at 0. A bare exponential
        cannot express this -- any lambda > 0 reaches zero given enough time.
        """
        memory = make_memory(tag=ActionTag.CRIME_ARMED_ASSAULT)
        after_a_year = retention_after(
            memory, AgeBand.YOUNG_ADULT, 12.0 + 24 * 365, Weather.CLEAR
        )
        self.assertAlmostEqual(after_a_year, 0.85, places=2)
        # The point of the floor: still nameable, years later.
        self.assertGreater(after_a_year, TELEPHONE_THRESHOLD)

    def test_petty_theft_fades_to_nothing(self):
        """No floor for theft: the spec grants permanence only to violent acts,
        and a small floor would leave every shoplifting rumour alive forever."""
        memory = make_memory(tag=ActionTag.CRIME_THEFT)
        after_a_day = retention_after(memory, AgeBand.YOUNG_ADULT, 36.0, Weather.CLEAR)
        after_a_month = retention_after(memory, AgeBand.YOUNG_ADULT, 12.0 + 720, Weather.CLEAR)
        self.assertLess(after_a_day, TELEPHONE_THRESHOLD)
        self.assertLess(after_a_month, 0.01)

    def test_retention_is_monotonic_toward_its_floor(self):
        """Never overshoots the floor, never climbs back toward R_0."""
        memory = make_memory(tag=ActionTag.CRIME_ASSAULT)
        previous = 1.01
        for hour in [12.0 + i * 0.5 for i in range(1, 400)]:
            current = retention_after(memory, AgeBand.YOUNG_ADULT, hour, Weather.CLEAR)
            self.assertLessEqual(current, previous + 1e-9)
            self.assertGreaterEqual(current, 0.4 - 1e-9)
            previous = current

    def test_low_visibility_encodes_worse(self):
        """Midnight heavy rain: poor structural capture, so faster forgetting."""
        memory = make_memory(tag=ActionTag.CRIME_THEFT)
        noon = retention_after(memory, AgeBand.YOUNG_ADULT, 24.0, Weather.CLEAR)
        midnight_rain = retention_after(
            make_memory(tag=ActionTag.CRIME_THEFT), AgeBand.YOUNG_ADULT, 24.0, Weather.RAIN
        )
        # Compare at matched formation conditions by rebuilding both.
        noon_mem = make_memory(hour=12.0, tag=ActionTag.CRIME_THEFT)
        rain_mem = make_memory(hour=0.0, tag=ActionTag.CRIME_THEFT)
        formed_noon = retention_after(noon_mem, AgeBand.YOUNG_ADULT, 20.0, Weather.CLEAR)
        formed_rain = retention_after(rain_mem, AgeBand.YOUNG_ADULT, 8.0, Weather.RAIN)
        self.assertLess(formed_rain, formed_noon)
        self.assertTrue(noon > 0 or midnight_rain > 0)

    def test_senior_forgets_faster_than_young(self):
        """Spec's Age column is a decay *rate*: senior lambda 1.4 > young 1.0,
        so elders retain less. The column is easy to read backwards because
        retention is the number people expect to go up."""
        memory = make_memory(tag=ActionTag.CRIME_THEFT)
        young = retention_after(memory, AgeBand.YOUNG_ADULT, 24.0, Weather.CLEAR)
        senior = retention_after(memory, AgeBand.SENIOR, 24.0, Weather.CLEAR)
        self.assertLess(senior, young)

    def test_visibility_uses_time_of_day_not_absolute_elapsed_hour(self):
        """The same time-of-day must have the same lighting after each full day."""
        self.assertEqual(decay.visibility_modifier(12.0, Weather.CLEAR),
                         decay.visibility_modifier(36.0, Weather.CLEAR))
        self.assertEqual(decay.visibility_modifier(0.0, Weather.CLEAR),
                         decay.visibility_modifier(24.0, Weather.CLEAR))
        self.assertEqual(decay.visibility_modifier(36.0, Weather.CLEAR), 0.8)
        self.assertEqual(decay.visibility_modifier(24.0, Weather.CLEAR), 1.5)

    def test_future_timestamp_does_not_decay(self):
        memory = make_memory(hour=48.0)
        self.assertAlmostEqual(
            retention_after(memory, AgeBand.ADULT, 12.0, Weather.CLEAR), memory.initial_impact
        )


class TestTelephoneEffect(unittest.TestCase):
    def test_sharp_memory_transmits_the_name(self):
        rumour = retell(make_memory(retention=0.9))
        self.assertIsNotNone(rumour)
        self.assertEqual(rumour.target_entity_id, "player-402")

    def test_faint_memory_transmits_only_appearance(self):
        """Below threshold the witness cannot name the target -- spec's core rule."""
        rumour = retell(make_memory(retention=0.5))
        self.assertIsNotNone(rumour)
        self.assertIsNone(rumour.target_entity_id)

    def test_almost_gone_memory_is_not_transmitted_at_all(self):
        self.assertIsNone(retell(make_memory(retention=0.01)))

    def test_chain_degrades_to_appearance_only(self):
        """End-to-end: the chain the vision doc describes.

        Time advances between hops, because that is what actually erodes memory.
        Transferring a rumour does not reset its clock -- the receiver inherits the
        transmitter's *current* retention and keeps decaying from there.
        """
        npcs = [NPC(entity_id=f"npc-{i}", age_band=AgeBand.YOUNG_ADULT) for i in range(12)]
        npcs[0].remember(make_memory(witness="npc-0", retention=1.0))

        hour = 12.0
        for speaker, listener in zip(npcs, npcs[1:]):
            hour += 2.0
            for npc in (speaker, listener):
                npc.memories = decay.sweep(
                    npc.memories, npc.age_band, hour, Weather.CLEAR
                )
            converse(listener, speaker)

        final = npcs[-1].memories
        self.assertTrue(final, "rumour died before the last link")
        self.assertIsNone(
            final[0].target_entity_id,
            "rumour still named the player after 11 hops -- decay too slow",
        )

    def test_short_chain_keeps_the_name(self):
        """Two hops should not yet have destroyed attribution."""
        npcs = [NPC(entity_id=f"p{i}") for i in range(3)]
        npcs[0].remember(make_memory(witness="p0", retention=1.0))
        for speaker, listener in zip(npcs, npcs[1:]):
            converse(listener, speaker)
        self.assertEqual(npcs[-1].memories[0].target_entity_id, "player-402")

    def test_older_witness_produces_a_shorter_reach(self):
        """Emergent consequence, pinned deliberately.

        Age compounds across every hop, so a crime a senior citizen witnessed
        travels materially less far than the same crime witnessed by a young
        adult -- old enough and the rumour dies before reaching a patrol at all.
        Crimes with elderly witnesses go effectively unreported.

        That is a defensible reading of the spec's Age column, but it is a
        consequence rather than a decision anyone made, so it is asserted here
        to make it visible instead of leaving it to be discovered later as an
        unexplained bug.
        """
        def reach(band):
            npcs = [NPC(entity_id=f"a{i}", age_band=band) for i in range(12)]
            npcs[0].remember(make_memory(witness="a0", retention=1.0))
            hour = 12.0
            last = 0
            for index, (speaker, listener) in enumerate(zip(npcs, npcs[1:])):
                hour += 2.0
                for npc in (speaker, listener):
                    npc.memories = decay.sweep(npc.memories, npc.age_band, hour, Weather.CLEAR)
                converse(listener, speaker)
                if listener.memories:
                    last = index + 1
            return last

        self.assertGreater(reach(AgeBand.YOUNG_ADULT), reach(AgeBand.SENIOR))


class TestDescriptionDistribution(unittest.TestCase):
    def test_single_hearing_stays_vague(self):
        desc = retell(make_memory(retention=0.9)).description
        self.assertIn("tall-ish", desc.describe())

    def test_corroboration_narrows_height_uncertainty(self):
        a = Description(height_m=1.8, height_uncertainty_m=0.3)
        b = Description(height_m=1.8, height_uncertainty_m=0.3)
        merged = a.merge(b)
        self.assertAlmostEqual(merged.height_m, 1.8, places=6)
        # Quadrature: sqrt(0.3^2+0.3^2) < 0.3 for two, never below the floor.
        self.assertLess(merged.height_uncertainty_m, 0.3)

    def test_jacket_confidence_rises_with_agreement(self):
        """Starts genuinely unsure -- two colours close to even -- then a third
        report of the same colour makes it decisive."""
        unsure = Description(
            height_m=1.8,
            jacket_colour_weights={"black": 1.0, "brown": 1.0},
            masked=False,
            masked_confidence=0.9,
        )
        self.assertAlmostEqual(unsure.jacket_confidence, 0.5)

        two = unsure.merge(Description(jacket_colour_weights={"black": 1.0}))
        self.assertGreater(two.jacket_confidence, unsure.jacket_confidence)
        self.assertGreater(two.jacket_confidence, 0.5)

    def test_disagreement_dilutes_rather_than_picks_winner(self):
        """Two witnesses insisting on different colours must not produce false
        certainty in either."""
        a = Description(jacket_colour_weights={"black": 1.0, "brown": 1.0})
        b = a.merge(Description(jacket_colour_weights={"white": 2.0}))
        self.assertLess(b.jacket_confidence, 1.0)

    def test_masked_state_survives_disagreement(self):
        """"Maybe masked" must stay maybe, not collapse to a hard False."""
        a = Description(masked=True, masked_confidence=0.9)
        b = a.merge(Description(masked=False, masked_confidence=0.3))
        self.assertLess(b.masked_confidence, 0.7)
        self.assertGreater(b.masked_confidence, 0.3)
        self.assertIn("maybe masked", b.describe())

    def test_contradiction_never_yields_a_confident_claim(self):
        """Two witnesses insisting on opposite facts must leave the rumour
        undecided -- never silently resolved in favour of one of them."""
        a = Description(masked=True, masked_confidence=0.9)
        b = a.merge(Description(masked=False, masked_confidence=0.9))
        self.assertLess(b.masked_confidence, 0.5)
        self.assertNotIn("masked", b.describe())

    def test_repeated_agreement_raises_masked_confidence(self):
        a = Description(masked=True, masked_confidence=0.6)
        b = a.merge(Description(masked=True, masked_confidence=0.6))
        self.assertGreater(b.masked_confidence, a.masked_confidence)

    def test_empty_description_has_zero_confidence(self):
        self.assertEqual(Description().jacket_confidence, 0.0)

    def test_positional_construction_still_maps_to_the_right_fields(self):
        """Guard against silent field-reorder corruption.

        Adding a defaulted field mid-list makes `Description(1.8, 0.3, {...},
        False, 0.9)` bind the colour dict to the wrong attribute and raise
        nothing at all. This test fails loudly if that ever happens again.
        """
        d = Description(1.8, 0.3, {"black": 0.8}, False, 0.9)
        self.assertEqual(d.height_m, 1.8)
        self.assertEqual(d.height_uncertainty_m, 0.3)
        self.assertIsInstance(d.jacket_colour_weights, dict)
        self.assertIs(d.masked, False)
        self.assertEqual(d.masked_confidence, 0.9)
        self.assertEqual(d.observations, 1)


class TestDesperationScale(unittest.TestCase):
    """Regression suite for the DI / MoralShackle scale mismatch."""

    def test_di_is_normalised_zero_to_one(self):
        calm = District("d", overpopulation=0.0, supply_shortage=0.0,
                        weather_severity=0.0, local_corruption=0.0)
        crisis = District("d", overpopulation=1.0, supply_shortage=1.0,
                          weather_severity=1.0, local_corruption=1.0)
        self.assertAlmostEqual(desperation_index(calm), 0.0)
        self.assertAlmostEqual(desperation_index(crisis), 1.0)

    def test_moderate_stress_does_not_criminalise_everyone(self):
        """The spec's raw DI hit 1.38 at stress 0.3, flipping a 0.95 paragon."""
        district = District("d", overpopulation=0.3, supply_shortage=0.3,
                            weather_severity=0.3, local_corruption=0.3)
        paragon = NPC(entity_id="honest", moral_shackle=0.95)
        self.assertFalse(evaluate(paragon, district).illegal)

    def test_shackle_actually_gates_the_flip(self):
        district = District("d", overpopulation=0.6, supply_shortage=0.6,
                            weather_severity=0.3, local_corruption=0.3)
        di = desperation_index(district)
        self.assertFalse(evaluate(NPC(entity_id="a", moral_shackle=di + 0.1), district).illegal)
        self.assertTrue(evaluate(NPC(entity_id="b", moral_shackle=di - 0.1), district).illegal)

    def test_ends_of_shackle_range_are_distinguishable(self):
        district = District("d", overpopulation=0.75, supply_shortage=0.75,
                            weather_severity=0.5, local_corruption=0.5)
        criminal = evaluate(NPC(entity_id="c", moral_shackle=0.2), district)
        honest = evaluate(NPC(entity_id="h", moral_shackle=0.95), district)
        self.assertTrue(criminal.illegal)
        self.assertFalse(honest.illegal)


class TestIllegalBranches(unittest.TestCase):
    def test_hunger_and_absence_of_police_shoplifts(self):
        d = District("d", overpopulation=0.4, supply_shortage=0.65,
                     weather_severity=0.0, local_corruption=0.2, security_presence=0.3)
        self.assertEqual(evaluate(NPC("n", moral_shackle=0.1), d).branch, "Shoplift")

    def test_severe_shortage_escalates_to_cargo_hijack(self):
        d = District("d", overpopulation=0.4, supply_shortage=0.85,
                     weather_severity=0.0, local_corruption=0.2, security_presence=0.3)
        self.assertEqual(evaluate(NPC("n", moral_shackle=0.1), d).branch, "CargoHijack")

    def test_corrupt_and_crowded_pressures_turn_to_syndicate(self):
        d = District("d", overpopulation=0.8, supply_shortage=0.4,
                     weather_severity=0.0, local_corruption=0.6, security_presence=0.5)
        self.assertEqual(evaluate(NPC("n", moral_shackle=0.1), d).branch, "JoinSyndicate")

    def test_legal_life_reports_no_branch(self):
        d = District("d")
        self.assertIsNone(evaluate(NPC("n"), d).branch)


class TestPoliceResponse(unittest.TestCase):
    def test_unattributable_rumour_produces_a_stop_not_an_arrest(self):
        rumour = retell(make_memory(retention=0.5))
        action = police_response(rumour, "District 4")
        self.assertIn("stop and search", action.lower())

    def test_attributable_rumour_produces_pursuit(self):
        rumour = retell(make_memory(retention=0.9))
        self.assertIn("pursue identification", police_response(rumour, "District 4"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
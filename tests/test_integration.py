"""End-to-end integration.

The unit tests prove each sub-engine in isolation. This proves they compose --
that a district collapsing produces the rumour, the arrest, the file, the plea, and
the betrayal, without any step contradicting the last.

Also serves as the executable specification for `docs/BLUEPRINT.md`: if this
scenario changes shape, the architecture changed.
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
    converse,
    decay,
    districts as ds,
    fixers as fx,
    justice as ju,
    trauma as tr,
)
from simreality.ecosystem import apply_district_pressure, desperation_index


def witness_memory(target="player", retention=1.0, tag=ActionTag.CRIME_THEFT, hour=12.0):
    return NPCMemory("witness", target, retention, retention, hour, tag,
                     Description(1.82, 0.28, {"black": 0.8}, False, 0.85))


class TestDistrictCollapse(unittest.TestCase):
    """A district under sustained pressure degrades, scars, and turns."""

    def test_overcrowded_ungoverned_district_in_a_storm_collapses(self):
        d = District("D4", population=400, capacity=100, security_presence=0.0)

        start_di = desperation_index(d)
        for _ in range(120):
            ds.tick_day(d, weather_severity=1.0)

        self.assertGreater(desperation_index(d), start_di)
        self.assertTrue(d.scar_active, "a collapsing district never scarred")
        self.assertGreater(d.scar_intensity, 0.5)

    def test_scarcity_alone_does_not_scar_a_district(self):
        """Crowding and corruption are not sufficient.

        Equilibrium DI with 4x overpopulation and no policing plateaus near 0.78
        in clear weather -- below SCAR_ENTER_DI. A ruined district has to be
        ruined by something compounding, or the threshold means nothing.
        """
        d = District("D4", population=400, capacity=100, security_presence=0.0)
        for _ in range(200):
            ds.tick_day(d, weather_severity=0.0)

        self.assertGreater(d.local_corruption, 0.9, "should still be thoroughly corrupt")
        self.assertLess(desperation_index(d), ds.SCAR_ENTER_DI)
        self.assertFalse(d.scar_active)

    def test_collapse_turns_residents_and_raises_trauma(self):
        d = District("D4", population=400, capacity=100, security_presence=0.0)
        citizens = [NPC(f"c{i}", moral_shackle=0.5) for i in range(5)]
        d.residents = citizens

        for _ in range(120):
            ds.tick_day(d, weather_severity=1.0)
            apply_district_pressure(d)
            for citizen in citizens:
                tr.daily_update(citizen, citizen.desperation_index)

        self.assertTrue(
            any(c.trauma_level.value > tr.TraumaLevel.BASELINE.value for c in citizens),
            "120 days of collapse left every citizen unperturbed",
        )

    def test_corruption_is_sticky_not_self_clearing(self):
        """Structural premise: a district cannot be cleaned up by arresting
        the right people, so corruption must not decay readily."""
        d = District("D4", population=400, capacity=100, security_presence=0.0)
        for _ in range(150):
            ds.evolve_inputs(d, 0.1)
        peak = d.local_corruption

        # Now restore order completely and let it breathe.
        d.population, d.capacity = 1, 1000
        d.security_presence = 1.0
        for _ in range(30):
            ds.evolve_inputs(d, 0.0)

        self.assertGreater(d.local_corruption, peak * 0.5,
                           "corruption collapsed after 30 calm days")


class TestRumorToProsecution(unittest.TestCase):
    """Crime -> witness -> gossip -> degraded rumour -> stop, or charge."""

    def test_witness_becomes_vigilante_when_world_collapses(self):
        """A victimised shopkeeper in a collapsed district. Brief Level 3, end to end."""
        d = District("D4", population=400, capacity=100, security_presence=0.0)
        for _ in range(120):
            ds.tick_day(d, weather_severity=1.0)
        self.assertGreater(desperation_index(d), 0.9)

        victim = NPC("shopkeeper")
        tr.absorb(victim, ActionTag.CRIME_ARMED_ASSAULT, was_victim=True)
        result = tr.assess(victim, desperation_index(d))

        self.assertEqual(result.level, tr.TraumaLevel.VIGILANTE)
        self.assertTrue(result.permanent)

    def test_a_collapsed_district_makes_bystanders_vigilantes(self):
        """Environmental collapse alone is sufficient -- the brief's Level 3 is civic."""
        d = District("D4", population=400, capacity=100, security_presence=0.0)
        for _ in range(120):
            ds.tick_day(d, weather_severity=1.0)

        bystander = NPC("bystander")
        result = tr.assess(bystander, desperation_index(d))
        self.assertEqual(result.level, tr.TraumaLevel.VIGILANTE)
        self.assertEqual(result.source, "environment")

    def test_short_gossip_chain_still_names_the_player(self):
        npcs = [NPC(f"n{i}", age_band=AgeBand.ADULT) for i in range(4)]
        npcs[0].remember(witness_memory())

        hour = 12.0
        for speaker, listener in zip(npcs, npcs[1:]):
            hour += 2.0
            for npc in (speaker, listener):
                npc.memories = decay.sweep(npc.memories, npc.age_band, hour, Weather.CLEAR)
            converse(listener, speaker)

        final = npcs[-1].memories[0]
        self.assertEqual(final.target_entity_id, "player")

        criminal_file = ju.file_from_memories("player", [final])
        self.assertTrue(criminal_file.is_prosecutable(), "named accused failed to charge")

    def test_long_chain_yields_a_stop_not_a_charge(self):
        """The design's signature failure, end to end.

        A rumour that has crossed a district is still a real crime, but by then it
        names nobody. The patrol can act on the description; the file cannot be
        built from it.
        """
        # Young adults, not ADULT: the age multiplier compounds across every hop, and
        # at 1.2 an ADULT chain dies before hop 12. That is the documented
        # age consequence (see TestDecayEquation in the other suite), so this
        # scenario pins the youngest band to get the longest chain.
        npcs = [NPC(f"n{i}", age_band=AgeBand.YOUNG_ADULT) for i in range(12)]
        npcs[0].remember(witness_memory())

        hour = 12.0
        for speaker, listener in zip(npcs, npcs[1:]):
            hour += 2.0
            for npc in (speaker, listener):
                npc.memories = decay.sweep(npc.memories, npc.age_band, hour, Weather.CLEAR)
            converse(listener, speaker)

        final = npcs[-1].memories[0]
        self.assertIsNone(final.target_entity_id)

        criminal_file = ju.file_from_memories("player", [final])
        self.assertFalse(criminal_file.is_prosecutable())
        self.assertEqual(criminal_file.sentence_if_convicted(), 0)
        self.assertIsNone(ju.plea_offer(criminal_file))

    def test_bribe_attempt_survives_a_collapsed_district(self):
        """Corruption does not soften the one offence that punishes bribery.

        In a district where police ignore everything, this charge is the only
        thing holding the rule together -- so it must be unconditional.
        """
        d = District("D4", population=400, capacity=100, security_presence=0.0)
        for _ in range(120):
            ds.tick_day(d, weather_severity=1.0)
        self.assertGreater(desperation_index(d), 0.9)

        criminal_file = ju.CriminalFile("player")
        ju.register_bribe_attempt(criminal_file)
        offer = ju.plea_offer(criminal_file)

        self.assertIsNotNone(offer)
        self.assertEqual(offer.offered_charge.evidence, "confessed")

    def test_corrupt_district_ignores_theft_but_not_shooting(self):
        corrupt = 0.95
        theft = ju.enforcement_probability(ActionTag.CRIME_THEFT, corrupt)
        shooting = ju.enforcement_probability(ActionTag.CRIME_ARMED_ASSAULT, corrupt)
        self.assertLess(theft, 0.15)
        self.assertGreater(shooting, 0.85)


class TestUnderworldChain(unittest.TestCase):
    """Bribe refusal -> fixer -> betrayal -> the file it creates."""

    def test_direct_bribe_then_fixer_can_still_end_in_ambush(self):
        d = District("D4", overpopulation=0.9, supply_shortage=0.9,
                     local_corruption=0.9, security_presence=0.05)

        criminal_file = ju.CriminalFile("player")
        ju.register_bribe_attempt(criminal_file)
        self.assertTrue(criminal_file.is_prosecutable())

        fixer = fx.FixerProfile("fixer-d4", "D4", standing=0.3, warrants=0.8)
        outcomes = [
            fx.negotiate("player", fixer, d, bribe=0.8, reputation=0.7, rng=i / 12.0)
            for i in range(12)
        ]
        self.assertTrue(any(o.betrayed for o in outcomes),
                        "betrayal never fired across the whole rng range")

        for outcome in outcomes:
            if outcome.betrayed:
                self.assertTrue(outcome.bribe_paid)
                self.assertTrue(outcome.squeal_filed)
            self.assertTrue(outcome.bribe_paid)

    def test_player_can_be_ambushed_without_being_charged(self):
        """A fixer who betrays has committed no offence against the player.

        The charge comes from the *crime*, not the betrayal -- so the player can
        be set up by a fixer while their file stays clean. The ambush has to be
        survivable or unevadable through skill.
        """
        d = District("D4", overpopulation=0.9, supply_shortage=0.9,
                     local_corruption=0.9, security_presence=0.05)
        fixer = fx.FixerProfile("f", "D4", standing=0.2, warrants=1.0)
        result = fx.negotiate("player", fixer, d, bribe=1.0, reputation=0.9, rng=0.0)
        self.assertTrue(result.betrayed)
        self.assertEqual(ju.CriminalFile("player").is_prosecutable(), False)

    def test_betrayal_rate_falls_as_the_network_grows(self):
        """Exposure is the counterweight the brief never supplied.

        One district, one bribe, one warrant depth -- standing is the only
        variable, so this isolates the effect. The district is stressed but not
        collapsed (DI 0.55), because at peak desperation the drive term dominates
        and every connected fixer squelches anyway, which would hide the effect
        this test exists to pin.
        """
        d = District("D4", overpopulation=0.55, supply_shortage=0.55,
                     local_corruption=0.55, security_presence=0.5)
        self.assertGreater(desperation_index(d), 0.3)

        exposed = fx.negotiate("player", fx.FixerProfile("a", "D4", standing=0.9, warrants=0.9),
                              d, bribe=1.0, reputation=0.9, rng=0.0)
        anonymous = fx.negotiate("player", fx.FixerProfile("b", "D4", standing=fx.FIXER_MIN_STANDING,
                                                          warrants=0.9),
                                 d, bribe=1.0, reputation=0.9, rng=0.0)
        self.assertFalse(exposed.betrayed)
        self.assertTrue(anonymous.betrayed)

    def test_peak_pressure_makes_a_connected_fixer_risky(self):
        """The dramatic case has to be possible.

        With the exposure term too heavy, a well-connected fixer under real
        pressure could never betray anybody -- the mechanic only fired for
        fixers with no standing, which is backwards.
        """
        d = District("D4", overpopulation=0.9, supply_shortage=0.9,
                     local_corruption=0.9, security_presence=0.05)
        p = fx.betrayal_probability(desperation_index(d), bribe=1.0,
                                    warrants=0.9, standing=0.9)
        self.assertGreater(p, 0.0)
        self.assertGreater(p, fx.betrayal_probability(desperation_index(d), bribe=0.05,
                                                      warrants=0.9, standing=0.9))


if __name__ == "__main__":
    unittest.main(verbosity=2)
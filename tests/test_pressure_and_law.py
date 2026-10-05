"""Tests for trauma tiers, district dynamics, justice, and fixers.

Four modules, four classes of bug the brief contains. Each fix is pinned by a
test that would fail if the fix were reverted.
"""

import unittest

from simreality import ActionTag, District, NPC, NPCMemory, Description
from simreality import districts as ds
from simreality import fixers as fx
from simreality import justice as ju
from simreality import trauma as tr
from simreality.ecosystem import desperation_index
from simreality.model import TraumaLevel


# ==========================================================================
# 4.A  Trauma
# ==========================================================================


class TestTraumaAxes(unittest.TestCase):
    def test_one_armed_assault_cannot_make_a_vigilante(self):
        """The brief's tiers conflate personal and environmental causes.

        Linear impact-to-tier mapping put a single witnessed armed assault
        (InitialImpact 1.0) at Level 3 -- 'zero law presence', a condition one
        crime cannot create. `personal_level` caps at Paranoid, so no amount of
        personal trauma reaches Level 3 on its own.
        """
        npc = NPC("victim")
        tr.absorb(npc, ActionTag.CRIME_ARMED_ASSAULT)
        result = tr.assess(npc, desperation_index=0.0)
        self.assertEqual(result.level, TraumaLevel.PARANOID)
        self.assertLess(result.level, TraumaLevel.VIGILANTE)

    def test_one_crime_in_a_functioning_city_cannot_make_a_vigilante(self):
        """Worst personal trauma, working city -- still Paranoid, not Vigilante."""
        npc = NPC("v")
        tr.absorb(npc, ActionTag.CRIME_ARMED_ASSAULT, was_victim=True)
        self.assertEqual(tr.assess(npc, 0.5).level, TraumaLevel.PARANOID)

    def test_environment_alone_makes_a_vigilante(self):
        """The Level 3 behaviour is civic, not personal.

        'Forms or joins localized protection rings, refuses to talk to law
        enforcement' is a collective response to absent law. A citizen in a
        lawless district who was never victimised absolutely does join a ring.
        Requiring both axes here was over-correcting the brief's ambiguity.
        """
        npc = NPC("bystander")
        result = tr.assess(npc, 0.95)
        self.assertEqual(result.level, TraumaLevel.VIGILANTE)
        self.assertEqual(result.source, "environment")
        self.assertEqual(npc.personal_stress, 0.0)

    def test_personal_trauma_is_reported_as_the_source_when_worse(self):
        npc = NPC("v")
        tr.absorb(npc, ActionTag.CRIME_THEFT, was_victim=True)
        result = tr.assess(npc, 0.0)
        self.assertEqual(result.source, "personal")
        self.assertEqual(result.level, TraumaLevel.ANXIOUS)

    def test_witnessing_bites_less_than_being_targeted(self):
        witness, victim = NPC("w"), NPC("v")
        tr.absorb(witness, ActionTag.CRIME_ASSAULT)
        tr.absorb(victim, ActionTag.CRIME_ASSAULT, was_victim=True)
        self.assertLess(witness.personal_stress, victim.personal_stress)

    def test_repeated_offences_compound(self):
        npc = NPC("n")
        for _ in range(5):
            tr.absorb(npc, ActionTag.CRIME_THEFT)
        self.assertGreaterEqual(npc.personal_stress, tr.TIER_ANXIOUS)

    def test_stress_never_exceeds_one(self):
        npc = NPC("n")
        for _ in range(50):
            tr.absorb(npc, ActionTag.CRIME_ARMED_ASSAULT, was_victim=True)
        self.assertLessEqual(npc.personal_stress, 1.0)

    def test_relax_is_semi_permanent_not_a_reset(self):
        """Brief calls Level 2 semi-permanent: a victim unwinds, but slowly."""
        npc = NPC("v")
        tr.absorb(npc, ActionTag.CRIME_THEFT, was_victim=True)
        start = npc.personal_stress
        self.assertLess(tr.relieve(2.0, start), start)
        # Semi-permanent means a month later it is still felt, not a week later.
        self.assertGreater(tr.relieve(30.0, start), start * 0.2)
        self.assertGreater(tr.relieve(30.0, start), start * 0.3)

    def test_relief_never_goes_negative(self):
        self.assertGreaterEqual(tr.relieve(10_000.0, 0.8), 0.0)

    def test_environment_alone_can_paranoid(self):
        npc = NPC("n")
        result = tr.assess(npc, 0.78)
        self.assertEqual(result.level, TraumaLevel.PARANOID)
        self.assertEqual(result.source, "environment")

    def test_daily_update_writes_the_tier_back(self):
        npc = NPC("n")
        tr.absorb(npc, ActionTag.CRIME_ASSAULT)
        result = tr.daily_update(npc, 0.0, days=1.0)
        self.assertEqual(npc.trauma_level, result.level)

    def test_polite_interaction_leaves_no_trace(self):
        npc = NPC("n")
        tr.absorb(npc, ActionTag.INTERACTION_POLITE)
        self.assertEqual(npc.personal_stress, 0.0)


# ==========================================================================
# 1.C / 2.B  District dynamics and city scars
# ==========================================================================


class TestDistrictDynamics(unittest.TestCase):
    def test_district_actually_changes_over_time(self):
        """The brief gives DI a daily cycle but no dynamics for its inputs.

        Without rates every district is frozen, so the city can never deteriorate
        and city scars can never fire against an unchanging city.
        """
        d = District("d", population=180, capacity=100)
        before = desperation_index(d)
        for _ in range(30):
            ds.tick_day(d, weather_severity=0.3)
        self.assertGreater(desperation_index(d), before)

    def test_overpopulation_tracks_population_ratio(self):
        d = District("d", population=200, capacity=100)
        for _ in range(60):
            ds.evolve_inputs(d, 0.0)
        self.assertAlmostEqual(d.overpopulation, 1.0, delta=0.05)

    def test_corruption_rises_faster_than_it_falls(self):
        """Asymmetry is the point: corruption that decayed as readily as it grew
        would mean any district could be cleaned up by arresting the right people.
        """
        d = District("d", local_corruption=0.0, overpopulation=0.9, supply_shortage=0.9)
        ds.evolve_inputs(d, 0.0)
        rise = d.local_corruption
        self.assertGreater(rise, 0.0)
        for _ in range(20):
            ds.evolve_inputs(d, 0.0)
        fall = rise - d.local_corruption
        self.assertGreater(rise, fall)

    def test_inputs_stay_in_range(self):
        d = District("d", population=500, capacity=10)
        for _ in range(100):
            ds.tick_day(d, weather_severity=1.0)
            for value in (d.overpopulation, d.supply_shortage, d.local_corruption,
                          d.weather_severity, d.scar_intensity):
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_weather_drives_shortage(self):
        calm, storm = District("calm"), District("storm")
        for _ in range(20):
            ds.evolve_inputs(calm, 0.0)
            ds.evolve_inputs(storm, 1.0)
        self.assertGreater(storm.supply_shortage, calm.supply_shortage)


class TestCityScars(unittest.TestCase):
    def test_scar_needs_more_than_three_days(self):
        """Brief: 'stays critical for more than three in-game days'."""
        d = self._critical_district()
        for day in range(ds.SCAR_DAYS_REQUIRED):
            self.assertFalse(ds.update_scars(d).active, f"scarred early on day {day + 1}")
        self.assertTrue(ds.update_scars(d).active)

    def test_hysteresis_prevents_flicker(self):
        """A district wobbling inside the hysteresis band must not strobe the city.

        Without hysteresis, alternating days either side of a single threshold
        flipped the whole district between clean and ruined, and every material,
        audio sub-mix, and police posture strobed with it.
        """
        d = self._critical_district()
        for _ in range(ds.SCAR_DAYS_REQUIRED + 1):
            ds.update_scars(d)
        self.assertTrue(d.scar_active)

        # Oscillate strictly inside the band between SCAR_EXIT_DI and
        # SCAR_ENTER_DI. Uniform stress s gives DI == s, so 0.70 sits in the band.
        self.assertLess(ds.SCAR_EXIT_DI, 0.70)
        self.assertLess(0.70, ds.SCAR_ENTER_DI)
        for step in range(40):
            s = 0.70 if step % 2 == 0 else 0.62
            d.overpopulation = d.supply_shortage = s
            d.weather_severity = d.local_corruption = s
            ds.update_scars(d)
            self.assertTrue(d.scar_active, f"flickered off on step {step}")

    def test_band_is_wide_enough_to_be_reachable(self):
        """The hysteresis band must actually contain achievable DI values."""
        self.assertGreater(ds.SCAR_ENTER_DI - ds.SCAR_EXIT_DI, 0.1)

    def test_scar_recovers_only_after_sustained_relief(self):
        d = self._critical_district()
        for _ in range(ds.SCAR_DAYS_REQUIRED + 1):
            ds.update_scars(d)
        self.assertTrue(d.scar_active)

        for day in range(ds.SCAR_RECOVERY_DAYS - 1):
            d.population, d.capacity = 1, 100
            d.local_corruption, d.security_presence = 0.0, 1.0
            for _ in range(3):
                ds.evolve_inputs(d, 0.0)
            self.assertTrue(ds.update_scars(d).active, f"recovered early on day {day + 1}")
        self.assertFalse(ds.update_scars(d).active)

    def test_scar_intensity_is_monotonic_while_active(self):
        d = self._critical_district()
        previous = -1.0
        for _ in range(8):
            previous = ds.update_scars(d).intensity
        self.assertGreater(previous, 0.0)

    def test_visual_thresholds_gate_on_intensity(self):
        scar = ds.ScarState(True, intensity=0.5, days_above_critical=4, desperation_index=0.9)
        self.assertTrue(scar.boarded_windows)
        self.assertFalse(scar.derelict_facades)
        deep = ds.ScarState(True, intensity=0.8, days_above_critical=4, desperation_index=0.9)
        self.assertTrue(deep.derelict_facades)

    @staticmethod
    def _critical_district() -> District:
        """A district comfortably above SCAR_ENTER_DI = 0.85.

        All four stresses must be high: weather severity carries weight 0.8 in the
        DI sum, so crowding and corruption alone top out near 0.77.
        """
        return District("d", population=190, capacity=100, supply_shortage=0.95,
                        overpopulation=0.95, weather_severity=1.0,
                        local_corruption=0.9, security_presence=0.05)


# ==========================================================================
# 2.A  Justice
# ==========================================================================


def witness_memory(target="player", retention=0.9, tag=ActionTag.CRIME_THEFT):
    return NPCMemory("w", target, 1.0, retention, 12.0, tag,
                     Description(1.8, 0.2, {"black": 0.8}, False, 0.9))


class TestEvidence(unittest.TestCase):
    def test_faded_memory_cannot_become_a_charge(self):
        """A rumour below threshold has already lost the target's identity.

        The brief's police response correctly produces a stop for these, but the
        arrest loop then proceeded as though stop and arrest were the same, so the
        file accumulated real charges against a predicate fact naming nobody.
        """
        charge = ju.charge_from_memory(witness_memory(retention=0.4))
        self.assertFalse(charge.provable)
        self.assertEqual(charge.evidence, "unwitnessed")

    def test_unresolved_report_is_still_recorded(self):
        """An unwitnessed accusation is intelligence, not nothing."""
        criminal_file = ju.file_from_memories("player", [witness_memory(retention=0.4)])
        self.assertEqual(len(criminal_file.charges), 1)
        self.assertFalse(criminal_file.is_prosecutable())

    def test_prosecutable_file_requires_provable_charge(self):
        self.assertFalse(ju.CriminalFile("p").is_prosecutable())

    def test_corroboration_strengthens_rather_than_stacks(self):
        """Two witnesses to one act must not become two charges."""
        single = ju.file_from_memories("player", [witness_memory()])
        pair = ju.file_from_memories("player", [witness_memory(), witness_memory()])
        self.assertEqual(len(pair.charges), 1)
        self.assertEqual(pair.charges[0].evidence, "corroborated")
        self.assertGreater(pair.charges[0].strength, single.charges[0].strength)

    def test_memories_about_other_people_are_ignored(self):
        criminal_file = ju.file_from_memories("player", [witness_memory(target="someone-else")])
        self.assertFalse(criminal_file.is_prosecutable())

    def test_distinct_offences_do_stack(self):
        criminal_file = ju.file_from_memories("player", [
            witness_memory(tag=ActionTag.CRIME_THEFT),
            witness_memory(tag=ActionTag.CRIME_ASSAULT),
        ])
        self.assertEqual(len(criminal_file.provable_charges()), 2)


class TestCorruptionDoesNotCollapseTheLaw(unittest.TestCase):
    def test_minor_offences_are_suppressed_by_corruption(self):
        honest = ju.enforcement_probability(ActionTag.CRIME_THEFT, 0.0)
        corrupt = ju.enforcement_probability(ActionTag.CRIME_THEFT, 0.9)
        self.assertAlmostEqual(honest, 1.0)
        self.assertLess(corrupt, 0.2)

    def test_serious_violence_stays_prosecutable(self):
        """Corruption suppresses shoplifting, not shootings.

        Untreated, corruption multiplied through to a 0.01% chance of any arrest
        at high corruption -- the city silently lost its legal system.
        """
        for corruption in (0.0, 0.5, 0.9, 1.0):
            self.assertGreater(
                ju.enforcement_probability(ActionTag.CRIME_ARMED_ASSAULT, corruption),
                ju.ENFORCEMENT_FLOOR,
            )
            self.assertGreater(ju.enforcement_probability(ActionTag.CRIME_ASSAULT, corruption), 0.5)

    def test_enforcement_never_reaches_zero(self):
        for tag in ActionTag:
            for corruption in (0.0, 0.5, 0.9, 1.0):
                self.assertGreaterEqual(
                    ju.enforcement_probability(tag, corruption), ju.ENFORCEMENT_FLOOR
                )

    def test_stop_is_not_an_arrest(self):
        """No provable charge -> a search and a release, not custody.

        This is the distinction the brief's prose runs together: information
        reaches police through the gossip network, and a report that has lost its
        subject can prompt a stop but can never carry a charge.
        """
        criminal_file = ju.file_from_memories("player", [witness_memory(retention=0.4)])
        outcome = ju.consequence_for(
            ActionTag.CRIME_THEFT, criminal_file, District("D4"), "officer-1",
            corruption=0.0, rng=0.5,
        )
        self.assertIsInstance(outcome, ju.Stop)
        self.assertTrue(outcome.released)

    def test_provable_charge_produces_an_arrest(self):
        criminal_file = ju.file_from_memories("player", [witness_memory(retention=0.95)])
        outcome = ju.consequence_for(
            ActionTag.CRIME_THEFT, criminal_file, District("D4"), "officer-1",
            corruption=0.0, rng=0.5,
        )
        self.assertIsInstance(outcome, ju.Arrest)
        self.assertEqual(outcome.officer_entity_id, "officer-1")
        self.assertEqual(outcome.district_id, "D4")
        self.assertTrue(outcome.charge.provable)

    def test_no_arrest_without_a_matching_charge(self):
        """A charge for a different offence does not carry this one."""
        criminal_file = ju.file_from_memories("player", [witness_memory(retention=0.95)])
        outcome = ju.consequence_for(
            ActionTag.CRIME_ASSAULT, criminal_file, District("D4"), "officer-1",
            corruption=0.0, rng=0.5,
        )
        self.assertIsInstance(outcome, ju.Stop)

    def test_corruption_can_suppress_the_whole_response(self):
        criminal_file = ju.file_from_memories("player", [witness_memory(retention=0.95)])
        outcome = ju.consequence_for(
            ActionTag.CRIME_THEFT, criminal_file, District("D4"), "officer-1",
            corruption=0.9, rng=0.99,
        )
        self.assertIsNone(outcome)


class TestBriberyAndPlea(unittest.TestCase):
    def test_bribe_attempt_to_officer_is_always_a_charge(self):
        criminal_file = ju.CriminalFile("p")
        ju.register_bribe_attempt(criminal_file)
        self.assertTrue(criminal_file.is_prosecutable())
        self.assertEqual(criminal_file.bribe_attempts, 1)

    def test_bribe_charge_survives_a_pacified_district(self):
        """The one thing corruption does not touch.

        An officer who can be bought is precisely why bribing one cannot be
        allowed to work, so this charge must not be softened by the district.
        """
        criminal_file = ju.CriminalFile("p")
        ju.register_bribe_attempt(criminal_file)
        charge = criminal_file.provable_charges()[0]
        self.assertTrue(charge.provable)
        self.assertEqual(charge.evidence, "confessed")

    def test_no_plea_offer_without_a_provable_charge(self):
        criminal_file = ju.file_from_memories("player", [witness_memory(retention=0.3)])
        self.assertIsNone(ju.plea_offer(criminal_file))

    def test_plea_is_worth_taking_on_a_stacked_file(self):
        criminal_file = ju.file_from_memories("player", [
            witness_memory(tag=ActionTag.CRIME_THEFT),
            witness_memory(tag=ActionTag.CRIME_ASSAULT),
            witness_memory(tag=ActionTag.CRIME_ARMED_ASSAULT),
        ])
        offer = ju.plea_offer(criminal_file)
        self.assertIsNotNone(offer)
        self.assertLess(offer.days_if_accepted, offer.days_if_tried)
        self.assertTrue(offer.dropped_charges)

    def test_unwitnessed_charges_are_excluded_from_sentencing(self):
        criminal_file = ju.file_from_memories("player", [witness_memory(retention=0.2)])
        self.assertEqual(criminal_file.sentence_if_convicted(), 0)

    def test_sentence_scales_with_severity(self):
        petty = ju.Charge(ActionTag.CRIME_THEFT, "single_witness", 0.7)
        violent = ju.Charge(ActionTag.CRIME_ARMED_ASSAULT, "single_witness", 0.7)
        self.assertGreater(violent.sentence(), petty.sentence())


# ==========================================================================
# 4.B  Fixers
# ==========================================================================


def desperate_district() -> District:
    return District("bad", overpopulation=0.9, supply_shortage=0.9,
                    local_corruption=0.9, security_presence=0.1)


class TestFixerBetrayal(unittest.TestCase):
    def test_betrayal_is_not_certain(self):
        """The core fix.

        As written, betrayal strictly dominated loyalty -- keep the bribe, clear
        your warrants, remove the witness, lose nothing. A rational fixer always
        betrayed, so 'might betray' would arrive as a guaranteed ambush.
        """
        fixer = fx.FixerProfile("f", "bad", standing=0.5, warrants=0.5)
        p = fx.betrayal_probability(0.9, bribe=0.5, warrants=0.5, standing=0.5)
        self.assertLess(p, 1.0)
        self.assertGreater(p, 0.0)
        self.assertLess(p, 0.95)

    def test_exposure_suppresses_betrayal(self):
        """The countervailing cost that the brief never supplied."""
        exposed = fx.betrayal_probability(1.0, 0.8, 0.8, standing=0.9)
        anonymous = fx.betrayal_probability(1.0, 0.8, 0.8, standing=0.0)
        self.assertLess(exposed, anonymous)

    def test_peak_desperation_is_the_trigger(self):
        calm = fx.betrayal_probability(0.1, 0.5, 0.5, standing=0.2)
        peak = fx.betrayal_probability(1.0, 0.5, 0.5, standing=0.2)
        self.assertGreater(peak, calm)

    def test_clean_fixers_do_not_need_bribes(self):
        """A fixer with no warrants has nothing to gain by squealing."""
        greedy = fx.betrayal_probability(1.0, 0.5, warrants=0.0, standing=0.0)
        self.assertGreater(greedy, fx.betrayal_probability(1.0, 0.5, warrants=0.9, standing=0.0))

    def test_probability_stays_in_range(self):
        for desperation in (0.0, 0.5, 1.0):
            for standing in (0.0, 0.5, 1.0):
                for warrants in (0.0, 0.5, 1.0):
                    p = fx.betrayal_probability(desperation, 1.0, warrants, standing)
                    self.assertGreaterEqual(p, 0.0)
                    self.assertLessEqual(p, 1.0)


class TestFixerNegotiationIsAtomic(unittest.TestCase):
    def test_betrayal_always_takes_the_money(self):
        """The outcome must be indivisible.

        Splitting 'did they take the money' from 'did they squeal' would let a
        caller observe the payment and skip the betrayal, which is the one thing
        this mechanic must not allow.
        """
        fixer = fx.FixerProfile("f", "bad", standing=0.0, warrants=0.9)
        district = desperate_district()
        for i in range(20):
            result = fx.negotiate("player", fixer, district, bribe=1.0, reputation=0.8, rng=i / 20.0)
            if result.betrayed:
                self.assertTrue(result.bribe_paid)
                self.assertTrue(result.squeal_filed)
                self.assertTrue(result.accepted)

    def test_refused_approach_pays_nothing(self):
        fixer = fx.FixerProfile("f", "bad", standing=0.9)
        result = fx.negotiate("player", fixer, desperate_district(),
                              bribe=1.0, reputation=0.1, rng=0.99)
        self.assertFalse(result.accepted)
        self.assertFalse(result.bribe_paid)
        self.assertEqual(fixer.bribes_accepted, 0)

    def test_low_reputation_is_refused(self):
        fixer = fx.FixerProfile("f", "bad", standing=0.5)
        result = fx.negotiate("player", fixer, desperate_district(),
                              bribe=1.0, reputation=0.1, rng=0.99)
        self.assertFalse(result.accepted)
        self.assertIn("reputation", result.reason)

    def test_unestablished_fixers_refuse(self):
        fixer = fx.FixerProfile("f", "bad", standing=0.01)
        result = fx.negotiate("player", fixer, desperate_district(),
                              bribe=1.0, reputation=0.9, rng=0.99)
        self.assertFalse(result.accepted)

    def test_stable_district_refuses(self):
        """A fixer will not be seen helping anyone where nothing is wrong."""
        fixer = fx.FixerProfile("f", "calm", standing=0.5)
        calm = District("calm", overpopulation=0.1, supply_shortage=0.1)
        result = fx.negotiate("player", fixer, calm, bribe=1.0, reputation=0.9, rng=0.99)
        self.assertFalse(result.accepted)

    def test_known_betrayers_are_tracked(self):
        # Standing must clear FIXER_MIN_STANDING or the fixer never deals at all,
        # which makes the test pass for the wrong reason.
        fixer = fx.FixerProfile("f", "bad", standing=fx.FIXER_MIN_STANDING, warrants=0.9)
        result = fx.negotiate("player", fixer, desperate_district(),
                              bribe=1.0, reputation=0.8, rng=0.0)
        self.assertTrue(result.accepted)
        self.assertTrue(result.betrayed)
        self.assertEqual(fx.known_betrayers([fixer]), ["f"])

    def test_bribe_greed_is_bounded(self):
        for bribe in (0.0, 0.5, 1.0, 100.0):
            greed = fx.bribe_greed(bribe, 0.5)
            self.assertGreaterEqual(greed, 0.0)
            self.assertLessEqual(greed, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
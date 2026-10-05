"""Tests for reputation and the fixer network.

Two gaps closed here: reputation had no source, and the fixer network was a list
of independent actors with no collective behaviour. Both were fixed by probing
the design numerically first, so these tests pin the probe findings rather than
the implementation -- see `docs/MATH-NOTES.md` bugs 15-18.
"""

import unittest

from simreality import ActionTag, AgeBand, Description, District, NPCMemory, Weather
from simreality import decay
from simreality import fixers as fx
from simreality import justice as ju
from simreality import reputation as rp
from simreality.ecosystem import desperation_index


def witness(target="player", retention=1.0, tag=ActionTag.CRIME_ASSAULT):
    return NPCMemory("w", target, retention, retention, 12.0, tag,
                     Description(1.8, 0.2, {"black": 0.8}, False, 0.9))


def stressed_district(di: float = 0.55) -> District:
    """A district at a chosen desperation index.

    `desperation_index` is a weight-normalised mean of the four stresses, so
    setting them all to the same value gives DI equal to that value. Lets a test
    choose the pressure it needs instead of hunting for a fixture that lands there.
    """
    return District("D4", overpopulation=di, supply_shortage=di,
                    local_corruption=di, weather_severity=di, security_presence=0.5)


def fade(mems, days, age_band=AgeBand.ADULT):
    """Decay memories the way the hourly sweep would over `days` of custody."""
    for hour in range(12, 12 + int(days) * 24, 2):
        mems = decay.sweep(mems, age_band, float(hour), Weather.CLEAR)
    return mems


# ==========================================================================
# Reputation
# ==========================================================================


class TestReputationIsDerived(unittest.TestCase):
    def test_conviction_outlives_the_rumour_that_convicted_you(self):
        """The custody paradox. The bug that made reputation have no point.

        Reputation computed purely from present evidence collapses the moment the
        evidence decays. Measured: five witnesses to an assault, all actionable,
        give reputation 0.51. Thirty days later, zero of those five are still
        actionable. A player convicted on that evidence therefore became locally
        respectable while serving the sentence -- the memory model erasing the
        social cost of the crime it had just proven.
        """
        mems = [witness() for _ in range(5)]
        criminal_file = ju.file_from_memories("player", mems)
        ju.convict(criminal_file, ActionTag.CRIME_ASSAULT, current_day=0, sentence_days=30)

        mems = fade(mems, 30)
        self.assertEqual(sum(1 for m in mems if m.is_actionable), 0,
                         "fixture no longer reproduces the paradox")

        profile = rp.local_reputation(mems, "player", criminal_file, current_day=60)
        self.assertLess(profile.reputation, 1.0)
        self.assertEqual(profile.source, "record")

    def test_unconvicted_fame_does_fade_with_the_memory(self):
        """The contrast case. Without a conviction, being talked about is enough.

        Reputation that could never recover would be its own kind of bug: the
        player is famous for a rumour, and the rumour is gone.
        """
        mems = fade([witness() for _ in range(5)], 30)
        self.assertEqual(rp.local_reputation(mems, "player").reputation, 1.0)

    def test_one_act_is_not_punished_twice(self):
        """An act produces both a witness memory and a conviction. Count it once.

        Summing them gave penalty 1.19, clamped to a reputation of exactly 0 --
        the same incident, punished twice, and unrecoverably.
        """
        mems = [witness(tag=ActionTag.CRIME_ASSAULT)]
        criminal_file = ju.file_from_memories("player", mems)
        ju.convict(criminal_file, ActionTag.CRIME_ASSAULT, current_day=0, sentence_days=30)

        profile = rp.local_reputation(mems, "player", criminal_file, current_day=0)
        self.assertLess(profile.reputation, 1.0)
        self.assertGreater(profile.reputation, 0.0)
        # The stronger of the two terms sets the penalty outright.
        self.assertGreater(profile.record_penalty, profile.accusation_penalty)
        self.assertAlmostEqual(profile.reputation, 1.0 - profile.record_penalty)

    def test_five_witnesses_to_one_act_is_one_act(self):
        """Corroboration dedupe, one layer up from the legal system.

        Five people witnessing one shoplifting is one act. Counting them separately
        compounded a single incident into a reputation collapse -- the same defect
        `justice.file_from_memories` was fixed for, repeating one layer out.
        """
        one = rp.accusation_penalty([witness(tag=ActionTag.CRIME_THEFT)], "player")
        five = rp.accusation_penalty(
            [witness(tag=ActionTag.CRIME_THEFT) for _ in range(5)], "player")
        self.assertAlmostEqual(one, five)

    def test_two_distinct_acts_do_compound(self):
        """Deduplication must not swallow genuinely separate offences."""
        both = rp.accusation_penalty(
            [witness(tag=ActionTag.CRIME_THEFT), witness(tag=ActionTag.CRIME_ASSAULT)],
            "player")
        single = rp.accusation_penalty([witness(tag=ActionTag.CRIME_THEFT)], "player")
        self.assertGreater(both, single)
        self.assertLess(both, 1.0)

    def test_a_faded_memory_cannot_accuse(self):
        """Below the telephone threshold the witness cannot name anybody.

        A player's standing propped up by accusations too vague to charge them
        with is the same defect the legal layer was fixed for.
        """
        self.assertEqual(rp.accusation_penalty([witness(retention=0.4)], "player"), 0.0)

    def test_memories_of_other_people_are_not_accusations(self):
        mems = [witness(target="somebody-else"), witness(target=None)]
        self.assertEqual(rp.accusation_penalty(mems, "player"), 0.0)

    def test_a_weak_recall_is_a_weaker_voice(self):
        """A witness who can barely still name the player carries less weight."""
        sharp = rp.accusation_penalty([witness(retention=1.0, tag=ActionTag.CRIME_THEFT)], "player")
        vague = rp.accusation_penalty([witness(retention=0.62, tag=ActionTag.CRIME_THEFT)], "player")
        self.assertGreater(sharp, vague)
        self.assertGreater(vague, 0.0)

    def test_a_crime_nobody_saw_costs_nothing(self):
        """No witness, no rumour, no reputation change. Correct by construction."""
        self.assertEqual(rp.accusation_penalty([], "player"), 0.0)


class TestConvictionRecord(unittest.TestCase):
    def test_a_conviction_never_fades_completely(self):
        """Public records do not disappear. They stop being current news."""
        criminal_file = ju.CriminalFile("player")
        ju.convict(criminal_file, ActionTag.CRIME_ASSAULT, current_day=0, sentence_days=30)
        ancient = rp.local_reputation([], "player", criminal_file, current_day=100_000)
        self.assertGreater(ancient.reputation, 0.8)
        self.assertLess(ancient.reputation, 1.0)

    def test_sentence_holds_the_conviction_at_full_weight(self):
        """It is fresh news while it is happening."""
        criminal_file = ju.CriminalFile("player")
        ju.convict(criminal_file, ActionTag.CRIME_ASSAULT, current_day=0, sentence_days=90)
        during = rp.record_penalty(criminal_file, current_day=45)
        after = rp.record_penalty(criminal_file, current_day=200)
        self.assertGreater(during, after)
        self.assertAlmostEqual(during, 0.7)

    def test_reputation_recovers_slowly_after_the_sentence(self):
        criminal_file = ju.CriminalFile("player")
        ju.convict(criminal_file, ActionTag.CRIME_ASSAULT, current_day=0, sentence_days=30)
        day_30 = rp.local_reputation([], "player", criminal_file, 30).reputation
        day_60 = rp.local_reputation([], "player", criminal_file, 60).reputation
        day_365 = rp.local_reputation([], "player", criminal_file, 365).reputation
        self.assertLess(day_30, day_60)
        self.assertLess(day_60, day_365)

    def test_only_the_most_recent_conviction_is_scored(self):
        """Summing convictions made a repeat offender permanently unemployable.

        That turns the fixer route off rather than making it expensive, which is a
        dead end instead of a cost.
        """
        criminal_file = ju.CriminalFile("player")
        ju.convict(criminal_file, ActionTag.CRIME_THEFT, current_day=0, sentence_days=10)
        ju.convict(criminal_file, ActionTag.CRIME_THEFT, current_day=1, sentence_days=10)
        ju.convict(criminal_file, ActionTag.CRIME_THEFT, current_day=2, sentence_days=10)
        one = rp.local_reputation([], "player", criminal_file, 3)
        self.assertAlmostEqual(one.record_penalty,
                               rp.record_penalty(
                                   ju.CriminalFile("player", convictions=[
                                       ju.Conviction(ActionTag.CRIME_THEFT, 2, 10)]), 3))

    def test_no_file_means_no_record(self):
        self.assertEqual(rp.record_penalty(None, 100), 0.0)
        self.assertEqual(rp.record_penalty(ju.CriminalFile("player"), 100), 0.0)

    def test_clean_when_nothing_is_on_record(self):
        profile = rp.local_reputation([], "player")
        self.assertTrue(profile.clean)
        self.assertEqual(profile.reputation, 1.0)

    def test_source_is_reported_for_debugging(self):
        mems = [witness(tag=ActionTag.CRIME_ASSAULT)]
        self.assertEqual(rp.local_reputation(mems, "player").source, "accusation")

        criminal_file = ju.CriminalFile("player")
        ju.convict(criminal_file, ActionTag.CRIME_ARMED_ASSAULT, 0, 0)
        self.assertEqual(rp.local_reputation(mems, "player", criminal_file, 0).source, "record")

    def test_stays_in_range(self):
        criminal_file = ju.CriminalFile("player")
        for tag in ActionTag:
            ju.convict(criminal_file, tag, 0, 0)
        for day in (0, 1, 30, 10_000):
            profile = rp.local_reputation(
                [witness(tag=t, retention=1.0) for t in ActionTag], "player",
                criminal_file, day)
            self.assertGreaterEqual(profile.reputation, 0.0)
            self.assertLessEqual(profile.reputation, 1.0)


# ==========================================================================
# The fixer network
# ==========================================================================


def network_of(count=4, standing=0.5, district_id="D4"):
    return fx.FixerNetwork(district_id, [
        fx.FixerProfile(f"f{i}", district_id, standing=standing, warrants=0.9)
        for i in range(count)
    ])


def betrayal():
    return fx.Negotiation(accepted=True, bribe_paid=True, betrayed=True,
                         reason="x", squeal_filed=True)


def clean():
    return fx.Negotiation(accepted=True, bribe_paid=True, betrayed=False, reason="x")


class TestNetworkPropagation(unittest.TestCase):
    def test_a_squealer_costs_their_peers(self):
        """The gap. A list of independent actors is not a network.

        Nothing was shared between fixers, so a player could be sold out six times
        over and the seventh would deal exactly as the first did.
        """
        d = stressed_district(0.7)
        net = network_of()
        before = [m.standing for m in net.members]

        net.record_outcome(net.members[0], betrayal(), d)

        self.assertLess(net.members[1].standing, before[1])
        self.assertLess(net.trust, 0.5)

    def test_a_well_connected_squealer_costs_more(self):
        """Blows the district's confidence by more than a nobody would."""
        d = stressed_district(0.7)
        prominent, obscure = network_of(), network_of()
        prominent.members[0].standing = 0.9
        obscure.members[0].standing = 0.25

        prominent.record_outcome(prominent.members[0], betrayal(), d)
        obscure.record_outcome(obscure.members[0], betrayal(), d)

        self.assertLess(prominent.trust, obscure.trust)

    def test_one_squealer_does_not_silence_the_district(self):
        d = stressed_district(0.9)
        net = network_of(count=6)
        net.record_outcome(net.members[0], betrayal(), d)
        self.assertGreater(net.trust, 0.0)

    def test_the_player_is_never_permanently_locked_out(self):
        """The one-way ratchet, and why the floor is load-bearing.

        Betrayal knocked peers below the standing at which they would deal;
        refusal means no deal; no deal means no betrayal to lose. Measured at any
        cost-per-betrayal from 0.1 upward, twelve betrayals in one district drove
        trust to exactly 0.00 with no path back. A player unlucky in one district
        could never fix anything again.
        """
        d = stressed_district(0.9)
        net = network_of()
        for _ in range(40):
            for member in net.members:
                net.record_outcome(member, betrayal(), d)

        self.assertTrue(all(m.standing >= fx.FIXER_MIN_STANDING for m in net.members),
                        "burned network fell below the threshold at which fixers deal")
        self.assertTrue(all(fx.willingness_to_deal(0.9, m, d)[0] for m in net.members))

    def test_refusals_do_not_damage_the_network(self):
        """A player turned away is not the network's problem."""
        d = stressed_district(0.7)
        net = network_of()
        before = net.trust
        net.record_outcome(net.members[0],
                           fx.Negotiation(False, False, False, "no deal"), d)
        self.assertEqual(net.trust, before)

    def test_a_clean_deal_restores_a_little(self):
        d = stressed_district(0.7)
        net = network_of()
        net.record_outcome(net.members[0], betrayal(), d)
        burned = net.trust
        net.record_outcome(net.members[1], clean(), d)
        self.assertGreater(net.trust, burned)

    def test_damage_outruns_repair(self):
        """Otherwise the mechanic has no lasting consequence."""
        # Scale to the actual cost of this betrayal rather than a fixed count, so
        # the assertion survives a retune of either constant.
        d = stressed_district(0.7)
        net = network_of(standing=0.9)
        before = net.trust
        net.record_outcome(net.members[0], betrayal(), d)
        burned = net.trust
        self.assertLess(burned, before)

        # Half the clean deals that would be needed to undo the betrayal must still
        # leave the network visibly damaged. Scoped to this betrayal's actual cost
        # so the assertion survives a retune of either constant.
        needed = (before - burned) / fx.CLEAN_DEAL_RECOVERY
        for _ in range(int(needed // 2) + 1):
            net.record_outcome(net.members[1], clean(), d)
        self.assertLess(net.trust, before)

    def test_a_burned_network_becomes_more_trigger_happy(self):
        """Emergent, and worth pinning.

        `p_betray` subtracts `EXPOSURE_WEIGHT * standing`, so a fixer with less
        standing is more exposed and more likely to squeal. Being burned therefore
        makes the *next* approach riskier, not safer. Word got around that
        squealing is safe here.
        """
        d = stressed_district(0.75)
        net = network_of(standing=0.9)
        p_before = fx.betrayal_probability(desperation_index(d), 1.0, 0.9, net.members[0].standing)
        for _ in range(20):
            for member in net.members:
                net.record_outcome(member, betrayal(), d)
            net.daily_update(d)
        p_after = fx.betrayal_probability(desperation_index(d), 1.0, 0.9, net.members[0].standing)

        self.assertLess(p_before, p_after)
        self.assertLess(p_after, 1.0)

    def test_betrayal_chains_converge_rather_than_runaway(self):
        """The feedback loop has to saturate."""
        d = stressed_district(0.85)
        net = network_of()
        for _ in range(50):
            for member in net.members:
                net.record_outcome(member, betrayal(), d)
            net.daily_update(d)
        self.assertTrue(all(0.0 <= m.standing <= 1.0 for m in net.members))
        self.assertGreater(net.trust, 0.0)


class TestNetworkCeiling(unittest.TestCase):
    def test_trust_cannot_peg_at_one(self):
        """Otherwise the network can be made permanently honest.

        Reliably dealing walked every member to 1.0, which contradicts the premise
        that fixing is unstable and removes any reason to watch your back.
        """
        d = stressed_district(0.95)
        net = network_of(standing=1.0)
        for _ in range(400):
            net.record_outcome(net.members[0], clean(), d)
            net.daily_update(d)
        self.assertLess(net.trust, 1.0)
        self.assertLessEqual(net.trust, net.ceiling(d) + 1e-9)

    def test_the_ceiling_scales_with_desperation(self):
        """A fixer network where nothing is wrong has no reason to be trusted."""
        calm, bad = stressed_district(0.35), stressed_district(0.95)
        net = network_of()
        self.assertLess(net.ceiling(calm), net.ceiling(bad))

    def test_peaceful_district_cannot_hold_a_trusted_network(self):
        d = stressed_district(0.2)
        net = network_of(standing=1.0)
        for _ in range(200):
            net.record_outcome(net.members[0], clean(), d)
            net.daily_update(d)
        self.assertLessEqual(net.trust, net.ceiling(d) + 1e-9)

    def test_damage_outlasts_the_next_few_fixers(self):
        """Sticky enough to matter where the player actually is.

        The window that matters is days, not months: a player who was just sold
        out walks to the next fixer in the same district. At the previous 0.06
        reversion the network was fully restored inside that window, so the
        propagation produced no observable difference between the first approach
        and the second.
        """
        # Standing 0.5 puts the resting state *above* the post-betrayal level, so
        # recovery is an upward move. (At standing 0.9 the betrayal pushed the
        # network below its resting state and it "recovered" downward, which
        # measures nothing.)
        d = stressed_district(0.7)
        net = network_of(standing=0.5)
        net.record_outcome(net.members[0], betrayal(), d)
        self.assertLess(net.trust, fx.TRUST_RESTING)

        for _ in range(20):
            net.daily_update(d)

        # 0.015 leaves this near 0.37; the old 0.06 reached 0.45, and a restored
        # network would be 0.50.
        self.assertLess(net.trust, 0.40,
                        "network forgot the betrayal before the player could try again")

    def test_standing_eventually_returns_to_resting(self):
        d = stressed_district(0.7)
        net = network_of()
        net.record_outcome(net.members[0], betrayal(), d)
        for _ in range(800):
            net.daily_update(d)
        self.assertAlmostEqual(net.trust, fx.TRUST_RESTING, delta=0.01)

    def test_trust_is_the_mean_of_its_members(self):
        """One source of truth. A parallel score would drift out of sync."""
        net = network_of(count=3, standing=0.6)
        self.assertAlmostEqual(net.trust, 0.6)
        self.assertEqual(fx.FixerNetwork("empty").trust, 0.0)

    def test_standing_stays_in_range_after_a_long_chaotic_run(self):
        d = stressed_district(0.8)
        net = network_of(count=5)
        for day in range(200):
            outcome = betrayal() if day % 3 == 0 else clean()
            for member in net.members:
                net.record_outcome(member, outcome, d)
            net.daily_update(d)
        for member in net.members:
            self.assertGreaterEqual(member.standing, fx.FIXER_MIN_STANDING)
            self.assertLessEqual(member.standing, 1.0)


# ==========================================================================
# Reputation feeding back into the fixer route
# ==========================================================================


class TestReputationIsConsumed(unittest.TestCase):
    """The gap being closed: `willingness_to_deal` read a reputation that
    nothing ever wrote, so every player sat permanently just above the floor."""

    def test_a_convicted_player_is_refused(self):
        criminal_file = ju.CriminalFile("player")
        ju.convict(criminal_file, ActionTag.CRIME_ARMED_ASSAULT, current_day=0, sentence_days=365)
        profile = rp.local_reputation([], "player", criminal_file, current_day=10)

        willing, reason = fx.willingness_to_deal(profile.reputation, fx.FixerProfile("f", "D4"), stressed_district(0.7))
        self.assertFalse(willing)
        self.assertIn("reputation", reason)

    def test_a_clean_player_is_accepted(self):
        profile = rp.local_reputation([], "player")
        willing, _ = fx.willingness_to_deal(profile.reputation, fx.FixerProfile("f", "D4"), stressed_district(0.7))
        self.assertTrue(willing)

    def test_the_squeal_that_betrays_you_eventually_closes_the_route(self):
        """The loop, closed.

        Betrayal files a tip -> clean police respond -> the player is charged,
        arrested, convicted -> their reputation falls -> the next fixer refuses.

        Before this existed, a fixer could betray the player every time and nothing
        about it ever stuck, because the reputation it should have damaged was a
        float that nothing wrote.
        """
        d = stressed_district(0.85)
        criminal_file = ju.CriminalFile("player")

        fixer = fx.FixerProfile("squealer", "D4", standing=fx.FIXER_MIN_STANDING, warrants=0.9)
        outcome = fx.negotiate("player", fixer, d, bribe=1.0, reputation=1.0, rng=0.0)
        self.assertTrue(outcome.betrayed)
        self.assertTrue(outcome.squeal_filed)

        # The tip reaches police, who still hold a witness who can name the player.
        mems = [witness(tag=ActionTag.CRIME_ARMED_ASSAULT, retention=1.0)]
        ju.file_from_memories("player", mems).charges
        criminal_file.charges = ju.file_from_memories("player", mems).charges

        arrest = ju.consequence_for(ActionTag.CRIME_ARMED_ASSAULT, criminal_file, d,
                                    "officer-1", corruption=0.0, rng=0.1)
        self.assertIsInstance(arrest, ju.Arrest)
        ju.convict(arrest.file, ActionTag.CRIME_ARMED_ASSAULT, current_day=0,
                   sentence_days=arrest.charge.sentence())

        profile = rp.local_reputation(mems, "player", arrest.file, current_day=5)
        self.assertLess(profile.reputation, fx.REPUTATION_FLOOR)

        for i in range(4):
            newcomer = fx.FixerProfile(f"f{i}", "D4", standing=0.6)
            willing, _ = fx.willingness_to_deal(profile.reputation, newcomer, d)
            self.assertFalse(willing, "a fresh fixer would still deal with a convicted player")

    def test_a_bribe_attempt_alone_does_not_lock_you_out(self):
        """Proportionate. Bribery is a 0.35-severity charge; it should sting."""
        criminal_file = ju.CriminalFile("player")
        ju.register_bribe_attempt(criminal_file)
        ju.convict(criminal_file, ActionTag.CRIME_THEFT, current_day=0, sentence_days=5)
        profile = rp.local_reputation([], "player", criminal_file, current_day=10)
        self.assertGreater(profile.reputation, fx.REPUTATION_FLOOR)
        self.assertLess(profile.reputation, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

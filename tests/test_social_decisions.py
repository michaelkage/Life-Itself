"""Tests for the trust-aware social-belief decision adapter."""
import unittest

from simreality.appraisal import ChoiceOption, NPCValueProfile
from simreality.beliefs import Evidence
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_decisions import SocialBeliefDecisionAdapter
from simreality.social_trust import SocialTrustLedger


class SocialBeliefDecisionTests(unittest.TestCase):
    def test_same_choices_rank_differently_from_observer_beliefs(self):
        trust = SocialTrustLedger({
            ("skeptic", "witness"): 0.1,
            ("supporter", "witness"): 0.9,
        })
        beliefs = SocialBeliefSystem(trust)
        report = Evidence("report", "guard-bribed", "witness", 1, 1.0, 1.0, 1)
        beliefs.observe("skeptic", report)
        beliefs.observe("supporter", report)
        options = [
            ChoiceOption("report", {"justice": 0.5}),
            ChoiceOption("protect", {"loyalty": 0.5}),
        ]
        effects = {"guard-bribed": {"justice": 1.0, "loyalty": -1.0}}
        justice_profile = NPCValueProfile("skeptic", {"justice": 1.0, "loyalty": 0.0})
        loyalty_profile = NPCValueProfile("supporter", {"justice": 0.0, "loyalty": 1.0})

        skeptic = SocialBeliefDecisionAdapter.rank(
            "skeptic", beliefs, justice_profile, options, value_effects=effects
        )
        supporter = SocialBeliefDecisionAdapter.rank(
            "supporter", beliefs, loyalty_profile, options, value_effects=effects
        )
        self.assertEqual(skeptic.preferred.choice_id, "report")
        self.assertEqual(supporter.preferred.choice_id, "protect")

    def test_adapter_is_read_only_and_ranking_is_stable(self):
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        beliefs.observe("npc", Evidence("e", "claim", "source", 1, 1.0, 1.0, 2))
        before = beliefs.snapshot()
        profile = NPCValueProfile("npc", {"safety": 1.0})
        options = [ChoiceOption("z", {"safety": 0.2}), ChoiceOption("a", {"safety": 0.2})]
        first = SocialBeliefDecisionAdapter.rank("npc", beliefs, profile, options)
        second = SocialBeliefDecisionAdapter.rank("npc", beliefs, profile, options)
        self.assertEqual(first, second)
        self.assertEqual(first.ranked[0].choice_id, "a")
        self.assertEqual(beliefs.snapshot(), before)

    def test_unknown_mapped_claim_is_not_silently_invented(self):
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        profile = NPCValueProfile("npc", {"safety": 1.0})
        with self.assertRaises(KeyError):
            SocialBeliefDecisionAdapter.rank(
                "npc", beliefs, profile, [ChoiceOption("x", {})],
                value_effects={"unknown-claim": {"safety": 1.0}},
            )

    def test_profile_must_belong_to_observer(self):
        with self.assertRaises(ValueError):
            SocialBeliefDecisionAdapter.rank(
                "npc-a", SocialBeliefSystem(SocialTrustLedger()),
                NPCValueProfile("npc-b", {}), [],
            )

    def test_empty_options_have_no_preferred_choice(self):
        result = SocialBeliefDecisionAdapter.rank(
            "npc", SocialBeliefSystem(SocialTrustLedger()),
            NPCValueProfile("npc", {}), [],
        )
        self.assertIsNone(result.preferred)
        self.assertEqual(result.ranked, ())


if __name__ == "__main__":
    unittest.main()

import unittest

from simreality.identity_evolution import IdentityChangeProposal
from simreality.scar_identity_proposals import (
    ScarIdentityProposalEvidence, ScarIdentityProposalLedger,
    ScarIdentityProposalSnapshot,
)


class ScarIdentityProposalPersistenceTests(unittest.TestCase):
    def setUp(self):
        proposal = IdentityChangeProposal(
            "event-1", "npc-1", "fear-response:scar-1", "trust",
            0.1, 0.12, 0.02, 0.8, "participant", 0.05,
        )
        self.evidence = ScarIdentityProposalEvidence(
            proposal, "scar-1", "fear-response", "fear", "crowded-room", 8, 0.8,
        )

    def test_exact_proposal_and_scar_provenance_round_trip(self):
        ledger = ScarIdentityProposalLedger()
        ledger.record(self.evidence)
        payload = ledger.snapshot().to_json()
        restored = ScarIdentityProposalSnapshot.from_json(payload)
        self.assertEqual(ScarIdentityProposalLedger.from_snapshot(restored).entries(), (self.evidence,))
        self.assertEqual(restored.to_json(), payload)

    def test_replay_is_idempotent_but_changed_provenance_is_rejected(self):
        ledger = ScarIdentityProposalLedger()
        ledger.record(self.evidence)
        ledger.record(self.evidence)
        self.assertEqual(len(ledger.entries()), 1)
        changed = ScarIdentityProposalEvidence(
            self.evidence.proposal, "scar-other", "fear-response",
            "fear", "crowded-room", 8, 0.8,
        )
        with self.assertRaises(ValueError):
            ledger.record(changed)

    def test_proposal_policy_key_must_encode_scar_identity(self):
        with self.assertRaises(ValueError):
            ScarIdentityProposalEvidence(
                self.evidence.proposal, "different-scar", "fear-response",
                "fear", "crowded-room", 8, 0.8,
            )


if __name__ == "__main__":
    unittest.main()

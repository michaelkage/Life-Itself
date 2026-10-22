#include "simreality/Information.h"

#include <cassert>
#include <cmath>
#include <limits>

using namespace simreality;

int main() {
    InformationLedger ledger;

    InformationClaim first;
    first.claim_id = "claim-1";
    first.subject_key = "bridge-7";
    first.proposition_key = "bridge-unsafe";
    first.root_evidence_id = "evidence-witness-a";
    first.source_entity_id = "witness-a";
    first.recipient_entity_id = "resident-b";
    first.created_tick = 10;
    first.confidence = 0.9;
    first.kind = InformationKind::Observation;

    assert(ledger.record(first).accepted);
    assert(ledger.size() == 1);
    assert(ledger.independent_evidence_count("bridge-7", "bridge-unsafe") == 1);
    assert(std::abs(ledger.independent_evidence_strength("bridge-7", "bridge-unsafe") - 0.9) < 1e-12);

    // Relaying the same underlying evidence must not create corroboration.
    assert(ledger.relay("claim-1", "claim-2", "resident-b", "resident-c", 11, 0.8).accepted);
    assert(ledger.relay("claim-2", "claim-3", "resident-c", "resident-d", 12, 0.5).accepted);
    assert(ledger.size() == 3);
    assert(ledger.independent_evidence_count("bridge-7", "bridge-unsafe") == 1);

    const InformationClaim* relayed = ledger.find("claim-3");
    assert(relayed != nullptr);
    assert(relayed->root_evidence_id == "evidence-witness-a");
    assert(relayed->hop_count == 2);
    assert(relayed->source_entity_id == "resident-c");
    assert(std::abs(relayed->confidence - 0.36) < 1e-12);

    // A genuinely separate evidence root can independently corroborate it.
    InformationClaim second = first;
    second.claim_id = "claim-4";
    second.root_evidence_id = "evidence-inspector-report";
    second.source_entity_id = "inspector";
    second.recipient_entity_id = "resident-c";
    second.created_tick = 13;
    second.confidence = 0.95;
    assert(ledger.record(second).accepted);
    assert(ledger.independent_evidence_count("bridge-7", "bridge-unsafe") == 2);
    assert(std::abs(ledger.independent_evidence_strength("bridge-7", "bridge-unsafe") - 0.995) < 1e-12);
    assert(std::abs(ledger.independent_evidence_strength_for_recipient("bridge-7", "bridge-unsafe", "listener") - 0.9) < 1e-12);
    assert(ledger.independent_evidence_strength_for_recipient("bridge-7", "bridge-unsafe", "uninformed") == 0.0);

    // Invalid or ambiguous lineage is rejected without mutating the ledger.
    const std::size_t before_invalid = ledger.size();
    assert(!ledger.record(first).accepted); // duplicate claim ID

    InformationClaim orphan = first;
    orphan.claim_id = "orphan";
    orphan.parent_claim_id = "missing-parent";
    orphan.hop_count = 1;
    assert(!ledger.record(orphan).accepted);

    InformationClaim forged_lineage = first;
    forged_lineage.claim_id = "forged-lineage";
    forged_lineage.parent_claim_id = "claim-1";
    forged_lineage.root_evidence_id = "different-root";
    forged_lineage.source_entity_id = "resident-b";
    forged_lineage.recipient_entity_id = "resident-x";
    forged_lineage.created_tick = 14;
    forged_lineage.hop_count = 1;
    assert(!ledger.record(forged_lineage).accepted);

    assert(!ledger.relay("claim-1", "bad-sender", "someone-else", "resident-x", 15, 0.8).accepted);
    assert(!ledger.relay("claim-1", "bad-fidelity", "resident-b", "resident-x", 15, 1.1).accepted);
    assert(!ledger.relay("claim-1", "bad-time", "resident-b", "resident-x", 9, 0.8).accepted);

    InformationClaim invalid_confidence = first;
    invalid_confidence.claim_id = "invalid-confidence";
    invalid_confidence.confidence = std::numeric_limits<double>::quiet_NaN();
    assert(!ledger.record(invalid_confidence).accepted);

    assert(ledger.size() == before_invalid);
    assert(ledger.find("claim-1") != nullptr);
    assert(ledger.find("missing-parent") == nullptr);

    // Corrections are separate historical claims; they do not erase the claim
    // they correct, and they retain the same evidence lineage.
    InformationClaim correction;
    correction.claim_id = "claim-correction";
    correction.subject_key = "bridge-7";
    correction.proposition_key = "bridge-safe-after-inspection";
    correction.root_evidence_id = "evidence-inspector-report";
    correction.parent_claim_id = "claim-4";
    correction.source_entity_id = "resident-c";
    correction.recipient_entity_id = "resident-d";
    correction.created_tick = 14;
    correction.confidence = 0.99;
    correction.hop_count = 1;
    correction.kind = InformationKind::Correction;
    assert(ledger.record(correction).accepted);
    assert(ledger.find("claim-4") != nullptr);
    assert(ledger.find("claim-correction") != nullptr);
    assert(ledger.independent_evidence_count("bridge-7", "bridge-unsafe") == 2);

    return 0;
}

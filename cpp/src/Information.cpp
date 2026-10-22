#include "simreality/Information.h"

#include <algorithm>
#include <cmath>
#include <utility>

namespace simreality {

ClaimResult InformationLedger::record(const InformationClaim& claim) {
    if (claim.claim_id.empty()) return {false, "claim_id must not be empty"};
    if (claim.subject_key.empty()) return {false, "subject_key must not be empty"};
    if (claim.proposition_key.empty()) return {false, "proposition_key must not be empty"};
    if (claim.root_evidence_id.empty()) return {false, "root_evidence_id must not be empty"};
    if (claim.source_entity_id.empty()) return {false, "source_entity_id must not be empty"};
    if (claim.recipient_entity_id.empty()) return {false, "recipient_entity_id must not be empty"};
    if (claim.created_tick < 0) return {false, "created_tick must be non-negative"};
    if (!std::isfinite(claim.confidence) || claim.confidence < 0.0 || claim.confidence > 1.0)
        return {false, "confidence must be finite and within [0, 1]"};
    if (claims_.find(claim.claim_id) != claims_.end())
        return {false, "claim_id already exists"};

    if (claim.parent_claim_id.empty()) {
        if (claim.hop_count != 0)
            return {false, "root claims must have hop_count zero"};
    } else {
        const auto parent_it = claims_.find(claim.parent_claim_id);
        if (parent_it == claims_.end())
            return {false, "parent claim must be recorded before its child"};

        const InformationClaim& parent = parent_it->second;
        if (claim.root_evidence_id != parent.root_evidence_id)
            return {false, "a relay must preserve root evidence identity"};
        if (claim.source_entity_id != parent.recipient_entity_id)
            return {false, "relay source must be the parent claim recipient"};
        if (claim.created_tick < parent.created_tick)
            return {false, "claim time cannot precede its parent"};
        if (parent.hop_count == UINT32_MAX || claim.hop_count != parent.hop_count + 1)
            return {false, "relay hop_count must be parent hop_count plus one"};
    }

    claims_.emplace(claim.claim_id, claim);
    return {true, {}};
}

ClaimResult InformationLedger::relay(
    const std::string& parent_claim_id,
    const std::string& new_claim_id,
    const std::string& sender_entity_id,
    const std::string& recipient_entity_id,
    const std::int64_t created_tick,
    const double transmission_fidelity) {
    const InformationClaim* parent = find(parent_claim_id);
    if (parent == nullptr) return {false, "parent claim does not exist"};
    if (sender_entity_id.empty() || recipient_entity_id.empty())
        return {false, "relay sender and recipient must not be empty"};
    if (parent->recipient_entity_id != sender_entity_id)
        return {false, "sender must have received the parent claim"};
    if (!std::isfinite(transmission_fidelity) ||
        transmission_fidelity < 0.0 || transmission_fidelity > 1.0)
        return {false, "transmission_fidelity must be finite and within [0, 1]"};
    if (parent->hop_count == UINT32_MAX)
        return {false, "hop_count limit reached"};

    InformationClaim child;
    child.claim_id = new_claim_id;
    child.subject_key = parent->subject_key;
    child.proposition_key = parent->proposition_key;
    child.root_evidence_id = parent->root_evidence_id;
    child.parent_claim_id = parent->claim_id;
    child.source_entity_id = sender_entity_id;
    child.recipient_entity_id = recipient_entity_id;
    child.created_tick = created_tick;
    child.confidence = parent->confidence * transmission_fidelity;
    child.hop_count = parent->hop_count + 1;
    child.kind = InformationKind::Report;
    return record(child);
}

const InformationClaim* InformationLedger::find(const std::string& claim_id) const noexcept {
    const auto it = claims_.find(claim_id);
    return it == claims_.end() ? nullptr : &it->second;
}

std::vector<InformationClaim> InformationLedger::lineage_for_claim(
    const std::string& claim_id) const {
    std::vector<InformationClaim> lineage;
    const InformationClaim* current = find(claim_id);
    while (current != nullptr) {
        lineage.push_back(*current);
        if (current->parent_claim_id.empty()) break;
        current = find(current->parent_claim_id);
    }
    if (lineage.empty() || !lineage.back().parent_claim_id.empty()) return {};
    std::reverse(lineage.begin(), lineage.end());
    return lineage;
}

std::vector<InformationClaim> InformationLedger::lineage_for_claim(
    const std::string& claim_id) const {
    std::vector<InformationClaim> lineage;
    const InformationClaim* current = find(claim_id);
    while (current != nullptr) {
        lineage.push_back(*current);
        if (current->parent_claim_id.empty()) break;
        current = find(current->parent_claim_id);
    }
    if (lineage.empty() || !lineage.back().parent_claim_id.empty()) return {};
    std::reverse(lineage.begin(), lineage.end());
    return lineage;
}

std::size_t InformationLedger::independent_evidence_count(
    const std::string& subject_key,
    const std::string& proposition_key) const {
    std::set<std::string> roots;
    for (const auto& [id, claim] : claims_) {
        (void)id;
        if (claim.subject_key == subject_key && claim.proposition_key == proposition_key)
            roots.insert(claim.root_evidence_id);
    }
    return roots.size();
}

double InformationLedger::independent_evidence_strength(
    const std::string& subject_key,
    const std::string& proposition_key) const {
    std::map<std::string, double> strongest_by_root;
    for (const auto& [id, claim] : claims_) {
        (void)id;
        if (claim.subject_key != subject_key || claim.proposition_key != proposition_key)
            continue;
        double& strongest = strongest_by_root[claim.root_evidence_id];
        strongest = std::max(strongest, claim.confidence);
    }

    // Noisy-OR combines distinct evidence roots while capping each root at its
    // strongest confidence. Retelling one claim can never add another factor.
    double remaining = 1.0;
    for (const auto& [root_id, confidence] : strongest_by_root) {
        (void)root_id;
        remaining *= (1.0 - confidence);
    }
    return std::clamp(1.0 - remaining, 0.0, 1.0);
}

double InformationLedger::independent_evidence_strength_for_recipient(
    const std::string& subject_key,
    const std::string& proposition_key,
    const std::string& recipient_entity_id) const {
    std::map<std::string, double> strongest_by_root;
    for (const auto& [id, claim] : claims_) {
        (void)id;
        if (claim.subject_key != subject_key || claim.proposition_key != proposition_key
            || claim.recipient_entity_id != recipient_entity_id) continue;
        double& strongest = strongest_by_root[claim.root_evidence_id];
        strongest = std::max(strongest, claim.confidence);
    }
    double remaining = 1.0;
    for (const auto& [root_id, confidence] : strongest_by_root) {
        (void)root_id;
        remaining *= (1.0 - confidence);
    }
    return std::clamp(1.0 - remaining, 0.0, 1.0);
}

} // namespace simreality

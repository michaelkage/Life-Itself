#pragma once

#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace simreality {

// Claims describe what an actor says or believes, not objective world truth.
// Corrections are new claims; historical claims remain in the ledger.
enum class InformationKind : std::uint8_t {
    Observation,
    Report,
    Inference,
    Correction
};

struct InformationClaim {
    std::string claim_id{};
    std::string subject_key{};
    std::string proposition_key{};
    std::string root_evidence_id{};
    std::string parent_claim_id{};
    std::string source_entity_id{};
    std::string recipient_entity_id{};
    std::int64_t created_tick{0};
    double confidence{0.5};
    std::uint32_t hop_count{0};
    InformationKind kind{InformationKind::Observation};
};

struct ClaimResult {
    bool accepted{false};
    std::string error{};
};

// Append-only provenance ledger. A relay is not independent corroboration:
// corroboration counts distinct root evidence IDs, not the number of times a
// claim has been repeated through a social network.
class InformationLedger {
public:
    [[nodiscard]] ClaimResult record(const InformationClaim& claim);

    [[nodiscard]] ClaimResult relay(
        const std::string& parent_claim_id,
        const std::string& new_claim_id,
        const std::string& sender_entity_id,
        const std::string& recipient_entity_id,
        std::int64_t created_tick,
        double transmission_fidelity);

    [[nodiscard]] const InformationClaim* find(const std::string& claim_id) const noexcept;
    // Returns the complete source-to-recipient chain, oldest claim first.
    // Missing claims return an empty chain; stored claims are append-only.
    [[nodiscard]] std::vector<InformationClaim> lineage_for_claim(
        const std::string& claim_id) const;
    // Returns the complete source-to-recipient chain, oldest claim first.
    // Missing claims return an empty chain; stored claims are append-only.
    [[nodiscard]] std::vector<InformationClaim> lineage_for_claim(
        const std::string& claim_id) const;
    [[nodiscard]] std::size_t independent_evidence_count(
        const std::string& subject_key,
        const std::string& proposition_key) const;
    // Returns a deterministic, bounded support estimate from distinct roots.
    // Each root contributes only its strongest recorded confidence, so relays
    // cannot inflate support. This is evidence strength, not objective truth.
    [[nodiscard]] double independent_evidence_strength(
        const std::string& subject_key,
        const std::string& proposition_key) const;
    // Recipient-scoped estimate: NPC belief updates must only use claims that
    // reached that NPC, never information elsewhere in the world.
    [[nodiscard]] double independent_evidence_strength_for_recipient(
        const std::string& subject_key,
        const std::string& proposition_key,
        const std::string& recipient_entity_id) const;
    [[nodiscard]] std::size_t size() const noexcept { return claims_.size(); }
    [[nodiscard]] const std::map<std::string, InformationClaim>& claims() const noexcept {
        return claims_;
    }

private:
    std::map<std::string, InformationClaim> claims_{};
};

} // namespace simreality

#pragma once

#include "simreality/CoreTypes.h"
#include "simreality/DecisionSystem.h"
#include "simreality/Districts.h"
#include "simreality/Ecosystem.h"
#include "simreality/Fixers.h"
#include "simreality/Gossip.h"
#include "simreality/LifeSystems.h"
#include "simreality/Information.h"
#include "simreality/Justice.h"
#include "simreality/RandomStream.h"
#include "simreality/Reputation.h"
#include "simreality/SimulationRuntime.h"
#include "simreality/Trauma.h"

#include <cstddef>
#include <cstdint>
#include <vector>

namespace simreality {

struct ResidentDayResult {
    EntityId entity_id{};
    BehaviourDecision behaviour{};
    TraumaAssessment trauma{};
};

struct DistrictDayResult {
    DistrictId district_id{};
    ScarState scars{};
    std::vector<ResidentDayResult> residents{};
};

struct WorldAdvanceReport {
    std::vector<ScheduledTick> ticks{};
    std::vector<DistrictDayResult> daily_results{};
    std::size_t memories_swept{0};
};

// Resolves a revision's saved claim ID to its ledger record and full relay chain.
// Unresolved IDs remain visible so missing provenance is not silently discarded.
struct BeliefEvidenceClaimExplanation {
    std::string requested_claim_id{};
    bool resolved{false};
    InformationClaim claim{};
    std::vector<InformationClaim> lineage{};
};

// Presentation-neutral explanation data; a signed delta is not a truth or
// morality score, only the change in this NPC's recorded confidence.
struct BeliefRevisionExplanation {
    BeliefRevision revision{};
    double confidence_delta{0.0};
    std::vector<BeliefEvidenceClaimExplanation> evidence_claims{};
};

// One current interpretation paired with only the revisions that explain that
// same action account and event time. This is not a claim about objective truth.
struct BeliefAccountExplanation {
    NPCBelief current_belief{};
    std::vector<BeliefRevisionExplanation> revisions{};
};

// Read-only joined view of information delivered to one NPC and their separate
// interpretations. Empty sections mean no records are available, not disproof.
struct NPCInvestigationView {
    EntityId npc_id{};
    std::vector<InvestigationGroup> received_information{};
    std::vector<NPCBelief> current_beliefs{};
    // Per-account explanations avoid making callers join revisions by hand.
    // Each account retains incompatible interpretations and their own history.
    std::vector<BeliefAccountExplanation> belief_accounts{};
    std::vector<BeliefRevisionExplanation> belief_history{};
};

 // Current read-only context for comparing moral options. This is a present-time
// view, not a historical decision record: it must not reconstruct earlier knowledge.
struct NPCDecisionContextExplanation {
    EntityId npc_id{};
    SimulationHour observed_at_hour{0.0};
    NPCInvestigationView investigation{};
    std::map<EntityId, double> relationships{};
    std::vector<MoralChoiceExplanation> option_explanations{};
};

// Portable coordinator for deterministic, simulation-time-driven world updates.
// Unreal-facing code should consume snapshots/reports rather than enter this core.
class SimulationWorld {
public:
    explicit SimulationWorld(
        WorldState initial_state = {}, double initial_hour = 0.0,
        std::uint64_t random_seed = 1U);

    [[nodiscard]] WorldState& state() noexcept { return state_; }
    [[nodiscard]] const WorldState& state() const noexcept { return state_; }
    [[nodiscard]] std::vector<FixerNetwork>& fixer_networks() noexcept {
        return fixer_networks_;
    }
    [[nodiscard]] const std::vector<FixerNetwork>& fixer_networks() const noexcept {
        return fixer_networks_;
    }
    [[nodiscard]] double total_hours() const noexcept { return runtime_.total_hours(); }
    [[nodiscard]] std::uint64_t day_index() const noexcept { return runtime_.day_index(); }
    [[nodiscard]] RandomStream& random_stream() noexcept { return random_; }
    [[nodiscard]] LifeCoordinator& life_system() noexcept { return life_; }
    [[nodiscard]] const LifeCoordinator& life_system() const noexcept { return life_; }
    [[nodiscard]] std::uint64_t random_state() const noexcept { return random_.state(); }
    [[nodiscard]] InformationLedger& information_ledger() noexcept { return information_; }
    [[nodiscard]] const InformationLedger& information_ledger() const noexcept { return information_; }

    // Read-only, presentation-agnostic belief history query. An empty target ID
    // returns all revisions for the NPC; results are chronologically ordered.
    [[nodiscard]] std::vector<BeliefRevision> belief_history_for(
        const EntityId& npc_id, const EntityId& target_id = {}) const;
    [[nodiscard]] std::vector<BeliefRevisionExplanation> belief_explanations_for(
        const EntityId& npc_id, const EntityId& target_id = {}) const;
    // Return every interpretation for one event, including incompatible accounts.
    [[nodiscard]] std::vector<NPCBelief> beliefs_about_event(
        const EntityId& npc_id, const EntityId& target_id,
        SimulationHour event_timestamp_hour) const;
    // Combines current accounts with revision history matching the exact target,
    // action interpretation, and event timestamp; accounts without revisions remain.
    [[nodiscard]] std::vector<BeliefAccountExplanation> belief_account_explanations_for(
        const EntityId& npc_id, const EntityId& target_id,
        SimulationHour event_timestamp_hour) const;
    // Join delivered claims, current interpretations, and chronological changes.
    // An optional target filters claim subject keys and belief target IDs.
    [[nodiscard]] NPCInvestigationView investigation_view_for(
        const EntityId& npc_id, const EntityId& target_id = {}) const;
    // Snapshot current evidence, beliefs, relationships, and option scores.
    // This is not historical decision context.
    [[nodiscard]] NPCDecisionContextExplanation decision_context_for(
        const EntityId& npc_id, const std::vector<MoralChoiceOption>& options,
        const EntityId& target_id = {}) const;
    // Resolves a scenario choice and records the inputs available at this moment.
    // Existing historical records are never reconstructed from later world state.
    [[nodiscard]] MoralChoiceResolution record_moral_choice(
        const EntityId& npc_id, const std::string& scenario_id,
        const std::vector<MoralChoiceOption>& options,
        const std::vector<MoralChoiceConsequence>& consequences);
    [[nodiscard]] std::vector<NPCDecisionRecord> decision_history_for(
        const EntityId& npc_id) const;

    // Advances simulation time in a frame-rate-independent way. All due hourly
    // memory sweeps and daily district/NPC updates run in chronological order.
    [[nodiscard]] WorldAdvanceReport advance(
        double elapsed_hours, Weather visibility_weather = Weather::Clear,
        double weather_severity = 0.0);
    [[nodiscard]] GhostInfluenceResult attempt_ghost_influence(
        const EntityId& ghost_id, const EntityId& npc_id,
        const std::string& action, double hour_of_day);

    // Social transfer is allowed only between NPCs currently assigned to the same
    // district. The resulting conversation mutates the listener's memory state.
    [[nodiscard]] Conversation talk(const EntityId& listener_id, const EntityId& speaker_id);

    // Reputation is derived from the district's saved beliefs, not treated as
    // objective truth. Cooperation and resource-sharing use that standing plus
    // the donor's personal relationship with the recipient.
    [[nodiscard]] double community_reputation(
        const EntityId& target_id, const DistrictId& district_id) const;
    [[nodiscard]] double cooperation_score(
        const EntityId& from_id, const EntityId& to_id) const;
    [[nodiscard]] bool offer_support(
        const EntityId& from_id, const EntityId& to_id, double amount);

    // Records one observed action in the witnesses' local memories and applies
    // personal stress to witnesses and, when supplied, the victim.
    [[nodiscard]] std::size_t record_witnessed_action(
        const EntityId& actor_id, ActionTag action_tag, Description description,
        const std::vector<EntityId>& witness_ids, const EntityId& victim_id = {});
    [[nodiscard]] CriminalFile build_criminal_file(const EntityId& player_id) const;
    [[nodiscard]] ReputationProfile reputation_in_district(
        const DistrictId& district_id, const EntityId& player_id,
        const CriminalFile* criminal_file = nullptr) const;
    [[nodiscard]] Consequence resolve_offence(
        const DistrictId& district_id, const EntityId& player_id,
        ActionTag action_tag, const EntityId& officer_id, CriminalFile& criminal_file);
    [[nodiscard]] Negotiation approach_fixer(
        const DistrictId& district_id, const EntityId& player_id,
        const EntityId& fixer_id, double bribe, const CriminalFile* criminal_file = nullptr);

private:
    [[nodiscard]] NPC& find_npc(const EntityId& entity_id);
    [[nodiscard]] const NPC& find_npc(const EntityId& entity_id) const;

    WorldState state_{};
    std::vector<FixerNetwork> fixer_networks_{};
    SimulationRuntime runtime_;
    RandomStream random_;
    LifeCoordinator life_{};
    InformationLedger information_{};
};

} // namespace simreality

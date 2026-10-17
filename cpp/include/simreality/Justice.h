#pragma once

#include "simreality/CoreTypes.h"

#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace simreality {

enum class EvidenceKind { Unwitnessed, SingleWitness, Corroborated, Confessed };

struct Charge {
    ActionTag action_tag{ActionTag::InteractionPolite};
    EvidenceKind evidence{EvidenceKind::Unwitnessed};
    double strength{0.0};

    [[nodiscard]] double severity() const noexcept;
    [[nodiscard]] bool provable() const noexcept;
    [[nodiscard]] double sentence() const noexcept;
};

struct Conviction {
    ActionTag action_tag{ActionTag::InteractionPolite};
    std::uint32_t convicted_on_day{0};
    double sentence_days{0.0};

    [[nodiscard]] double severity() const noexcept;
};

struct CriminalFile {
    EntityId player_id{};
    std::vector<Charge> charges{};
    std::vector<ActionTag> confessions{};
    std::vector<Conviction> convictions{};
    std::uint32_t bribe_attempts{0};

    [[nodiscard]] double severity_total() const noexcept;
    [[nodiscard]] double sentence_if_convicted() const noexcept;
    [[nodiscard]] std::vector<Charge> provable_charges() const;
    [[nodiscard]] bool is_prosecutable() const noexcept;
    [[nodiscard]] const Conviction* most_recent_conviction() const noexcept;
};

struct Stop {
    std::string reason{};
    bool released{true};
};

// The file pointer is non-owning and remains valid while the caller-owned file lives.
struct Arrest {
    const CriminalFile* file{nullptr};
    Charge charge{};
    EntityId officer_entity_id{};
    DistrictId district_id{};
};

using Consequence = std::variant<std::monostate, Stop, Arrest>;

struct PleaOffer {
    Charge offered_charge{};
    std::vector<Charge> dropped_charges{};
    double days_if_accepted{0.0};
    double days_if_tried{0.0};
    std::string note{};
};

inline constexpr double kMinorOffenceCutoff = 0.45;
inline constexpr double kEnforcementFloor = 0.12;

[[nodiscard]] Charge charge_from_memory(const NPCMemory& memory);
[[nodiscard]] CriminalFile file_from_memories(
    const EntityId& player_id, const std::vector<NPCMemory>& memories);
[[nodiscard]] Conviction convict(
    CriminalFile& criminal_file, ActionTag action_tag,
    std::uint32_t current_day, double sentence_days);
void register_bribe_attempt(CriminalFile& criminal_file);
[[nodiscard]] double enforcement_probability(ActionTag action_tag, double corruption) noexcept;
[[nodiscard]] Consequence consequence_for(
    ActionTag action_tag, const CriminalFile& criminal_file, const District& district,
    const EntityId& officer_entity_id, double corruption, double rng);
[[nodiscard]] std::optional<PleaOffer> plea_offer(const CriminalFile& criminal_file);

} // namespace simreality

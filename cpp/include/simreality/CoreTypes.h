#pragma once

// Engine-independent data contract for the Simulated Reality Engine.
// Keep Unreal types (UObject, FVector, UWorld, etc.) out of this header.

#include <algorithm>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace simreality {

using EntityId = std::string;
using DistrictId = std::string;
using SimulationHour = double;

enum class ActionTag {
    InteractionPolite,
    CrimeTheft,
    CrimeAssault,
    CrimeArmedAssault,
    CrimeVandalism
};

enum class AgeBand { YoungAdult, Adult, Senior };
enum class Weather { Clear, HeavyRain };
enum class TraumaLevel { Baseline = 0, Anxious = 1, Paranoid = 2, Vigilante = 3 };

struct Description {
    double height_m{0.0};
    double height_uncertainty_m{0.35};
    std::map<std::string, double> jacket_colour_weights{};
    bool masked{false};
    double masked_confidence{0.0};
    // Keep this last: preserving positional field order avoids silent port bugs.
    std::uint32_t observations{1};
};

struct NPCMemory {
    EntityId witness_id{};
    EntityId target_entity_id{}; // Empty means the target is no longer attributable.
    double initial_impact{1.0};
    double retention{1.0};
    SimulationHour timestamp_hour{0.0};
    ActionTag action_tag{ActionTag::InteractionPolite};
    Description description{};

    [[nodiscard]] bool is_actionable(double telephone_threshold = 0.6) const noexcept {
        return !target_entity_id.empty() && retention >= telephone_threshold;
    }
};

enum class DailyActivity : std::uint8_t { Home, Commute, Work, Shop, Socialise, Service, Leisure, Sleep };

struct ScheduleEntry { DailyActivity activity{DailyActivity::Sleep}; std::uint8_t start_hour{22}; std::uint8_t end_hour{6}; };

struct NPC {
    EntityId entity_id{};
    AgeBand age_band{AgeBand::Adult};
    double moral_shackle{0.8};
    double desperation_index{0.0};
    TraumaLevel trauma_level{TraumaLevel::Baseline};
    double personal_stress{0.0};
    std::vector<NPCMemory> memories{};
    // Appended to preserve the existing aggregate field order.
    DistrictId district_id{};
    EntityId home_id{};
    EntityId job_id{};
    DailyActivity current_activity{DailyActivity::Sleep};
    std::vector<ScheduleEntry> schedule{};
    std::map<EntityId, double> relationships{};
    std::vector<std::string> goals{};
    double money{100.0};
    double hourly_wage{0.0};
    double daily_rent{0.0};
};

struct District {
    DistrictId district_id{};
    double overpopulation{0.3};
    double supply_shortage{0.3};
    double weather_severity{0.0};
    double local_corruption{0.2};
    double security_presence{0.5};

    std::uint32_t population{30};
    std::uint32_t capacity{100};
    std::uint32_t days_above_critical{0};
    std::uint32_t days_recovering{0};
    bool scar_active{false};
    double scar_intensity{0.0};
    double shop_stock{1.0};
    double employment_rate{0.65};
    double housing_availability{0.25};
    double transport_reliability{0.8};
    double service_capacity{0.7};
    double cash_circulation{1000.0};
};

struct OngoingEvent {
    std::string event_id{};
    DistrictId district_id{};
    EntityId actor_id{};
    ActionTag action_tag{ActionTag::InteractionPolite};
    SimulationHour created_hour{0.0};
    double severity{0.0};
    std::vector<EntityId> witness_ids{};
    double investigation_progress{0.0};
    bool resolved{false};
};

struct WorldState {
    std::vector<NPC> npcs{};
    std::vector<District> districts{};
    std::vector<OngoingEvent> ongoing_events{};
};

} // namespace simreality

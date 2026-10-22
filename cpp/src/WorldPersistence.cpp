#include "simreality/WorldPersistence.h"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <istream>
#include <limits>
#include <ostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace simreality {
namespace {
constexpr std::array<char, 8> kMagicV5{{'S', 'R', 'E', 'C', 'O', 'R', 'E', '5'}};
constexpr std::array<char, 8> kMagicV6{{'S', 'R', 'E', 'C', 'O', 'R', 'E', '6'}};
constexpr std::array<char, 8> kMagicV7{{'S', 'R', 'E', 'C', 'O', 'R', 'E', '7'}};
constexpr std::array<char, 8> kMagicV8{{'S', 'R', 'E', 'C', 'O', 'R', 'E', '8'}};
constexpr std::array<char, 8> kMagicV9{{'S', 'R', 'E', 'C', 'O', 'R', 'E', '9'}};
constexpr std::array<char, 8> kMagicV10{{'S', 'R', 'E', 'C', 'O', 'R', 'E', 'A'}};
constexpr std::array<char, 8> kMagicV11{{'S', 'R', 'E', 'C', 'O', 'R', 'E', 'B'}};
constexpr std::array<char, 8> kMagicV12{{'S', 'R', 'E', 'C', 'O', 'R', 'E', 'C'}};
constexpr std::uint32_t kMaxCollectionItems = 1'000'000;
constexpr std::uint32_t kMaxStringBytes = 16U * 1024U * 1024U;
static_assert(sizeof(double) == sizeof(std::uint64_t));
static_assert(std::numeric_limits<double>::is_iec559);

void write_u8(std::ostream& out, std::uint8_t value) {
    out.put(static_cast<char>(value));
    if (!out) throw std::runtime_error("failed writing world snapshot");
}

void write_u32(std::ostream& out, std::uint32_t value) {
    for (unsigned int i = 0; i < 4; ++i) {
        write_u8(out, static_cast<std::uint8_t>((value >> (i * 8U)) & 0xffU));
    }
}

void write_u64(std::ostream& out, std::uint64_t value) {
    for (unsigned int i = 0; i < 8; ++i) {
        write_u8(out, static_cast<std::uint8_t>((value >> (i * 8U)) & 0xffU));
    }
}

void write_count(std::ostream& out, std::size_t count) {
    if (count > kMaxCollectionItems) {
        throw std::length_error("world snapshot collection exceeds item limit");
    }
    write_u32(out, static_cast<std::uint32_t>(count));
}

void write_double(std::ostream& out, double value) {
    if (!std::isfinite(value)) throw std::invalid_argument("cannot save non-finite world value");
    write_u64(out, std::bit_cast<std::uint64_t>(value));
}

void write_string(std::ostream& out, const std::string& value) {
    if (value.size() > kMaxStringBytes) {
        throw std::length_error("world snapshot string exceeds size limit");
    }
    write_u32(out, static_cast<std::uint32_t>(value.size()));
    out.write(value.data(), static_cast<std::streamsize>(value.size()));
    if (!out) throw std::runtime_error("failed writing world snapshot string");
}

std::uint8_t read_u8(std::istream& in) {
    const int value = in.get();
    if (value == std::char_traits<char>::eof()) {
        throw std::runtime_error("unexpected end of world snapshot");
    }
    return static_cast<std::uint8_t>(value);
}

std::uint32_t read_u32(std::istream& in) {
    std::uint32_t value = 0;
    for (unsigned int i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(read_u8(in)) << (i * 8U);
    }
    return value;
}

std::uint64_t read_u64(std::istream& in) {
    std::uint64_t value = 0;
    for (unsigned int i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(read_u8(in)) << (i * 8U);
    }
    return value;
}

double read_double(std::istream& in) {
    const double value = std::bit_cast<double>(read_u64(in));
    if (!std::isfinite(value)) throw std::runtime_error("snapshot contains a non-finite value");
    return value;
}

std::string read_string(std::istream& in) {
    const std::uint32_t size = read_u32(in);
    if (size > kMaxStringBytes) throw std::length_error("snapshot string exceeds size limit");
    std::string value(size, '\0');
    in.read(value.data(), static_cast<std::streamsize>(size));
    if (!in) throw std::runtime_error("unexpected end of world snapshot string");
    return value;
}

std::uint32_t read_count(std::istream& in) {
    const std::uint32_t count = read_u32(in);
    if (count > kMaxCollectionItems) {
        throw std::length_error("snapshot collection exceeds item limit");
    }
    return count;
}

template <typename Enum>
Enum read_enum(std::istream& in, std::uint8_t max_value, const char* name) {
    const std::uint8_t value = read_u8(in);
    if (value > max_value) throw std::runtime_error(std::string("invalid ") + name);
    return static_cast<Enum>(value);
}

void write_description(std::ostream& out, const Description& value) {
    write_double(out, value.height_m);
    write_double(out, value.height_uncertainty_m);
    write_count(out, value.jacket_colour_weights.size());
    for (const auto& [colour, weight] : value.jacket_colour_weights) {
        write_string(out, colour);
        write_double(out, weight);
    }
    write_u8(out, value.masked ? 1U : 0U);
    write_double(out, value.masked_confidence);
    write_u32(out, value.observations);
}

Description read_description(std::istream& in) {
    Description value;
    value.height_m = read_double(in);
    value.height_uncertainty_m = read_double(in);
    const std::uint32_t colours = read_count(in);
    for (std::uint32_t i = 0; i < colours; ++i) {
        const std::string colour = read_string(in);
        const double weight = read_double(in);
        if (!value.jacket_colour_weights.emplace(colour, weight).second) {
            throw std::runtime_error("duplicate jacket colour in snapshot");
        }
    }
    const std::uint8_t masked = read_u8(in);
    if (masked > 1U) throw std::runtime_error("invalid masked flag");
    value.masked = masked != 0U;
    value.masked_confidence = read_double(in);
    value.observations = read_u32(in);
    return value;
}

void write_memory(std::ostream& out, const NPCMemory& value) {
    write_string(out, value.witness_id);
    write_string(out, value.target_entity_id);
    write_double(out, value.initial_impact);
    write_double(out, value.retention);
    write_double(out, value.timestamp_hour);
    write_u8(out, static_cast<std::uint8_t>(value.action_tag));
    write_description(out, value.description);
}

NPCMemory read_memory(std::istream& in) {
    NPCMemory value;
    value.witness_id = read_string(in);
    value.target_entity_id = read_string(in);
    value.initial_impact = read_double(in);
    value.retention = read_double(in);
    value.timestamp_hour = read_double(in);
    value.action_tag = read_enum<ActionTag>(in, 8U, "action tag");
    value.description = read_description(in);
    return value;
}

void write_npc(std::ostream& out, const NPC& value) {
    write_string(out, value.entity_id);
    write_u8(out, static_cast<std::uint8_t>(value.age_band));
    write_double(out, value.moral_shackle);
    write_double(out, value.desperation_index);
    write_u8(out, static_cast<std::uint8_t>(value.trauma_level));
    write_double(out, value.personal_stress);
    write_count(out, value.memories.size());
    for (const NPCMemory& memory : value.memories) write_memory(out, memory);
    write_string(out, value.district_id);
    write_string(out, value.home_id); write_string(out, value.job_id);
    write_u8(out, static_cast<std::uint8_t>(value.current_activity));
    write_count(out, value.schedule.size());
    for (const ScheduleEntry& entry : value.schedule) {
        write_u8(out, static_cast<std::uint8_t>(entry.activity));
        write_u8(out, entry.start_hour); write_u8(out, entry.end_hour);
    }
    write_count(out, value.relationships.size());
    for (const auto& item : value.relationships) {
        write_string(out, item.first); write_double(out, item.second);
    }
    write_count(out, value.goals.size());
    for (const std::string& goal : value.goals) write_string(out, goal);
    write_double(out, value.money); write_double(out, value.hourly_wage);
    write_double(out, value.daily_rent);
    write_double(out, value.work_hours_today);
    write_u8(out, value.commute_disrupted_today ? 1U : 0U);
    write_u32(out, value.missed_work_days);
    write_double(out, value.lost_income);
    write_double(out, value.rent_arrears);
    write_double(out, value.social_need);
    write_double(out, value.isolation);
    write_count(out, value.beliefs.size());
    for (const NPCBelief& belief : value.beliefs) {
        write_string(out, belief.target_entity_id);
        write_u8(out, static_cast<std::uint8_t>(belief.action_tag));
        write_double(out, belief.timestamp_hour);
        write_double(out, belief.confidence);
        write_string(out, belief.source_entity_id);
        write_u8(out, belief.directly_observed ? 1U : 0U);
        write_u32(out, belief.corroborations);
        write_u32(out, belief.contradictions);
    }
    write_double(out, value.loyalty_bias);
    write_double(out, value.skepticism);
    write_double(out, value.compassion);
    write_double(out, value.fairness_value);
    write_double(out, value.safety_value);
    write_double(out, value.freedom_value);
    write_double(out, value.self_interest_value);
    write_count(out, value.belief_revision_history.size());
    for (const BeliefRevision& revision : value.belief_revision_history) {
        write_string(out, revision.target_entity_id);
        write_u8(out, static_cast<std::uint8_t>(revision.action_tag));
        write_double(out, revision.event_timestamp_hour);
        write_double(out, revision.previous_confidence);
        write_double(out, revision.revised_confidence);
        write_u8(out, static_cast<std::uint8_t>(revision.reason));
        write_string(out, revision.source_entity_id);
        write_double(out, revision.recorded_hour);
    }
}

NPC read_npc(std::istream& in, std::uint32_t version) {
    NPC value;
    value.entity_id = read_string(in);
    value.age_band = read_enum<AgeBand>(in, 2U, "age band");
    value.moral_shackle = read_double(in);
    value.desperation_index = read_double(in);
    value.trauma_level = read_enum<TraumaLevel>(in, 3U, "trauma level");
    value.personal_stress = read_double(in);
    const std::uint32_t memories = read_count(in);
    value.memories.reserve(memories);
    for (std::uint32_t i = 0; i < memories; ++i) value.memories.push_back(read_memory(in));
    value.district_id = read_string(in);
    value.home_id = read_string(in); value.job_id = read_string(in);
    value.current_activity = read_enum<DailyActivity>(in, 7U, "daily activity");
    const std::uint32_t schedules = read_count(in);
    for (std::uint32_t i = 0; i < schedules; ++i) {
        ScheduleEntry entry;
        entry.activity = read_enum<DailyActivity>(in, 7U, "scheduled activity");
        entry.start_hour = read_u8(in); entry.end_hour = read_u8(in);
        if (entry.start_hour > 23U || entry.end_hour > 23U) throw std::runtime_error("invalid schedule hour");
        value.schedule.push_back(entry);
    }
    const std::uint32_t relationships = read_count(in);
    for (std::uint32_t i = 0; i < relationships; ++i) {
        auto id = read_string(in); auto strength = read_double(in);
        if (!value.relationships.emplace(id, strength).second) throw std::runtime_error("duplicate relationship");
    }
    const std::uint32_t goals = read_count(in);
    for (std::uint32_t i = 0; i < goals; ++i) value.goals.push_back(read_string(in));
    value.money = read_double(in); value.hourly_wage = read_double(in); value.daily_rent = read_double(in);
    value.work_hours_today = read_double(in);
    const std::uint8_t commute_disrupted = read_u8(in);
    if (commute_disrupted > 1U) throw std::runtime_error("invalid commute-disrupted flag");
    value.commute_disrupted_today = commute_disrupted != 0U;
    value.missed_work_days = read_u32(in); value.lost_income = read_double(in);
    value.rent_arrears = read_double(in); value.social_need = read_double(in);
    value.isolation = read_double(in);
    if (version >= 8U) {
        const std::uint32_t beliefs = read_count(in);
        value.beliefs.reserve(beliefs);
        for (std::uint32_t i = 0; i < beliefs; ++i) {
            NPCBelief belief;
            belief.target_entity_id = read_string(in);
            belief.action_tag = read_enum<ActionTag>(in, 8U, "belief action");
            belief.timestamp_hour = read_double(in);
            belief.confidence = read_double(in);
            if (belief.confidence < 0.0 || belief.confidence > 1.0)
                throw std::runtime_error("invalid belief confidence");
            belief.source_entity_id = read_string(in);
            const std::uint8_t direct = read_u8(in);
            if (direct > 1U) throw std::runtime_error("invalid direct-observation flag");
            belief.directly_observed = direct != 0U;
            belief.corroborations = read_u32(in);
            belief.contradictions = read_u32(in);
            value.beliefs.push_back(std::move(belief));
        }
    }
    if (version >= 9U) {
        value.loyalty_bias = read_double(in);
        value.skepticism = read_double(in);
        value.compassion = read_double(in);
        if (value.loyalty_bias < 0.0 || value.loyalty_bias > 1.0
            || value.skepticism < 0.0 || value.skepticism > 1.0
            || value.compassion < 0.0 || value.compassion > 1.0) {
            throw std::runtime_error("invalid NPC personality trait");
        }
    }
    if (version >= 10U) {
        value.fairness_value = read_double(in);
        value.safety_value = read_double(in);
        value.freedom_value = read_double(in);
        value.self_interest_value = read_double(in);
        if (value.fairness_value < 0.0 || value.fairness_value > 1.0
            || value.safety_value < 0.0 || value.safety_value > 1.0
            || value.freedom_value < 0.0 || value.freedom_value > 1.0
            || value.self_interest_value < 0.0 || value.self_interest_value > 1.0) {
            throw std::runtime_error("invalid NPC moral value");
        }
    }
    if (version >= 12U) {
        const std::uint32_t revisions = read_count(in);
        value.belief_revision_history.reserve(revisions);
        for (std::uint32_t i = 0; i < revisions; ++i) {
            BeliefRevision revision;
            revision.target_entity_id = read_string(in);
            revision.action_tag = read_enum<ActionTag>(in, 8U, "revision action");
            revision.event_timestamp_hour = read_double(in);
            revision.previous_confidence = read_double(in);
            revision.revised_confidence = read_double(in);
            if (revision.previous_confidence < 0.0 || revision.previous_confidence > 1.0
                || revision.revised_confidence < 0.0 || revision.revised_confidence > 1.0)
                throw std::runtime_error("invalid belief revision confidence");
            revision.reason = read_enum<BeliefRevisionReason>(in, 2U, "belief revision reason");
            revision.source_entity_id = read_string(in);
            revision.recorded_hour = read_double(in);
            if (revision.event_timestamp_hour < 0.0 || revision.recorded_hour < 0.0)
                throw std::runtime_error("invalid belief revision timestamp");
            value.belief_revision_history.push_back(std::move(revision));
        }
    }
    return value;
}

void write_district(std::ostream& out, const District& value) {
    write_string(out, value.district_id);
    write_double(out, value.overpopulation);
    write_double(out, value.supply_shortage);
    write_double(out, value.weather_severity);
    write_double(out, value.local_corruption);
    write_double(out, value.security_presence);
    write_u32(out, value.population);
    write_u32(out, value.capacity);
    write_u32(out, value.days_above_critical);
    write_u32(out, value.days_recovering);
    write_u8(out, value.scar_active ? 1U : 0U);
    write_double(out, value.scar_intensity);
    write_double(out, value.shop_stock); write_double(out, value.employment_rate);
    write_double(out, value.housing_availability); write_double(out, value.transport_reliability);
    write_double(out, value.service_capacity); write_double(out, value.cash_circulation);
}

District read_district(std::istream& in) {
    District value;
    value.district_id = read_string(in);
    value.overpopulation = read_double(in);
    value.supply_shortage = read_double(in);
    value.weather_severity = read_double(in);
    value.local_corruption = read_double(in);
    value.security_presence = read_double(in);
    value.population = read_u32(in);
    value.capacity = read_u32(in);
    value.days_above_critical = read_u32(in);
    value.days_recovering = read_u32(in);
    const std::uint8_t scar_active = read_u8(in);
    if (scar_active > 1U) throw std::runtime_error("invalid scar-active flag");
    value.scar_active = scar_active != 0U;
    value.scar_intensity = read_double(in);
    value.shop_stock = read_double(in); value.employment_rate = read_double(in);
    value.housing_availability = read_double(in); value.transport_reliability = read_double(in);
    value.service_capacity = read_double(in); value.cash_circulation = read_double(in);
    return value;
}

void write_world_state(std::ostream& out, const WorldState& value) {
    write_count(out, value.npcs.size());
    for (const NPC& npc : value.npcs) write_npc(out, npc);
    write_count(out, value.districts.size());
    for (const District& district : value.districts) write_district(out, district);
    write_count(out, value.ongoing_events.size());
    for (const OngoingEvent& event : value.ongoing_events) {
        write_string(out, event.event_id); write_string(out, event.district_id);
        write_string(out, event.actor_id);
        write_u8(out, static_cast<std::uint8_t>(event.action_tag));
        write_double(out, event.created_hour); write_double(out, event.severity);
        write_count(out, event.witness_ids.size());
        for (const EntityId& witness : event.witness_ids) write_string(out, witness);
        write_double(out, event.investigation_progress);
        write_u8(out, event.resolved ? 1U : 0U);
    }
    write_count(out, value.businesses.size());
    for (const Business& business : value.businesses) {
        write_string(out, business.business_id);
        write_string(out, business.district_id);
        write_double(out, business.stock);
        write_double(out, business.stock_capacity);
        write_double(out, business.cash);
        write_double(out, business.restock_cost_per_unit);
        write_double(out, business.hourly_wage);
        write_u32(out, business.job_slots);
        write_u8(out, business.open ? 1U : 0U);
    }
    write_count(out, value.housing_units.size());
    for (const HousingUnit& unit : value.housing_units) {
        write_string(out, unit.unit_id); write_string(out, unit.district_id);
        write_u32(out, unit.capacity); write_double(out, unit.daily_rent);
        write_double(out, unit.condition);
    }
}

WorldState read_world_state(std::istream& in, std::uint32_t version) {
    WorldState value;
    const std::uint32_t npcs = read_count(in);
    value.npcs.reserve(npcs);
    for (std::uint32_t i = 0; i < npcs; ++i) value.npcs.push_back(read_npc(in, version));
    const std::uint32_t districts = read_count(in);
    value.districts.reserve(districts);
    for (std::uint32_t i = 0; i < districts; ++i) {
        value.districts.push_back(read_district(in));
    }
    const std::uint32_t events = read_count(in);
    value.ongoing_events.reserve(events);
    for (std::uint32_t i = 0; i < events; ++i) {
        OngoingEvent event;
        event.event_id = read_string(in); event.district_id = read_string(in);
        event.actor_id = read_string(in);
        event.action_tag = read_enum<ActionTag>(in, 8U, "event action");
        event.created_hour = read_double(in); event.severity = read_double(in);
        const std::uint32_t witnesses = read_count(in);
        for (std::uint32_t j = 0; j < witnesses; ++j) event.witness_ids.push_back(read_string(in));
        event.investigation_progress = read_double(in);
        const std::uint8_t resolved = read_u8(in);
        if (resolved > 1U) throw std::runtime_error("invalid event resolution flag");
        event.resolved = resolved != 0U;
        value.ongoing_events.push_back(std::move(event));
    }
    const std::uint32_t businesses = read_count(in);
    value.businesses.reserve(businesses);
    for (std::uint32_t i = 0; i < businesses; ++i) {
        Business business;
        business.business_id = read_string(in);
        business.district_id = read_string(in);
        business.stock = read_double(in);
        business.stock_capacity = read_double(in);
        business.cash = read_double(in);
        business.restock_cost_per_unit = read_double(in);
        business.hourly_wage = read_double(in);
        business.job_slots = read_u32(in);
        const std::uint8_t open = read_u8(in);
        if (open > 1U) throw std::runtime_error("invalid business-open flag");
        business.open = open != 0U;
        value.businesses.push_back(std::move(business));
    }
    const std::uint32_t housing_units = read_count(in);
    value.housing_units.reserve(housing_units);
    for (std::uint32_t i = 0; i < housing_units; ++i) {
        HousingUnit unit;
        unit.unit_id = read_string(in); unit.district_id = read_string(in);
        unit.capacity = read_u32(in); unit.daily_rent = read_double(in);
        unit.condition = read_double(in);
        value.housing_units.push_back(std::move(unit));
    }
    return value;
}

void write_network(std::ostream& out, const FixerNetwork& value) {
    write_string(out, value.district_id);
    write_count(out, value.members.size());
    for (const FixerProfile& member : value.members) {
        write_string(out, member.entity_id);
        write_string(out, member.district_id);
        write_double(out, member.standing);
        write_double(out, member.warrants);
        write_double(out, member.bribes_accepted);
        write_count(out, member.dealings.size());
        for (const std::string& dealing : member.dealings) write_string(out, dealing);
    }
}

FixerNetwork read_network(std::istream& in) {
    FixerNetwork value;
    value.district_id = read_string(in);
    const std::uint32_t members = read_count(in);
    value.members.reserve(members);
    for (std::uint32_t i = 0; i < members; ++i) {
        FixerProfile member;
        member.entity_id = read_string(in);
        member.district_id = read_string(in);
        member.standing = read_double(in);
        member.warrants = read_double(in);
        member.bribes_accepted = read_double(in);
        const std::uint32_t dealings = read_count(in);
        member.dealings.reserve(dealings);
        for (std::uint32_t j = 0; j < dealings; ++j) {
            member.dealings.push_back(read_string(in));
        }
        value.members.push_back(std::move(member));
    }
    return value;
}


void write_life_state(std::ostream& out, const LifeCoordinator& life) {
    write_count(out, life.characters().size());
    for (const auto& [id, character] : life.characters()) {
        write_string(out, id);
        write_u8(out, static_cast<std::uint8_t>(character.status));
        write_u64(out, character.death_day);
        write_string(out, character.death_cause);
        write_count(out, character.conditions.size());
        for (const MedicalCondition& condition : character.conditions) {
            write_string(out, condition.condition_id);
            write_double(out, condition.severity);
            write_double(out, condition.recovery_per_day);
            write_double(out, condition.work_capacity_at_full_severity);
            write_u8(out, condition.lasting_impairment ? 1U : 0U);
            write_double(out, condition.impairment_floor);
            write_double(out, condition.care_hours_per_severity);
        }
        write_count(out, character.treatments.size());
        for (const MedicalTreatment& treatment : character.treatments) {
            write_string(out, treatment.treatment_id);
            write_string(out, treatment.condition_id);
            write_double(out, treatment.effectiveness);
            write_double(out, treatment.daily_cost);
            write_double(out, treatment.complication_risk);
            write_u8(out, treatment.active ? 1U : 0U);
        }
        write_double(out, character.care_need_hours);
        write_double(out, character.lost_income);
        write_u32(out, character.missed_work_days);
        write_count(out, character.personality.size());
        for (const auto& [target, value] : character.personality) {
            write_string(out, target); write_double(out, value);
        }
        write_count(out, character.memories.size());
        for (const auto& [target, value] : character.memories) {
            write_string(out, target); write_double(out, value);
        }
    }
    write_count(out, life.obligations().size());
    for (const LifeObligation& obligation : life.obligations()) {
        write_string(out, obligation.obligation_id);
        write_string(out, obligation.debtor_id);
        write_string(out, obligation.creditor_id);
        write_double(out, obligation.amount_due);
        write_u64(out, obligation.due_day);
        write_u8(out, obligation.settled ? 1U : 0U);
        write_u8(out, obligation.missed ? 1U : 0U);
    }
    write_count(out, life.ghost_windows().size());
    for (const GhostTimeWindow& window : life.ghost_windows()) {
        write_double(out, window.start_hour);
        write_double(out, window.end_hour);
        write_double(out, window.strength);
        write_count(out, window.permitted_actions.size());
        for (const std::string& action : window.permitted_actions) write_string(out, action);
    }
}

void read_life_state(std::istream& in, LifeCoordinator& life, std::uint32_t version) {
    std::map<EntityId, LifeCharacter> characters;
    const std::uint32_t character_count = read_count(in);
    for (std::uint32_t i = 0; i < character_count; ++i) {
        LifeCharacter character;
        character.entity_id = read_string(in);
        character.status = read_enum<LifeStatus>(in, 3U, "life status");
        character.death_day = read_u64(in);
        character.death_cause = read_string(in);
        const std::uint32_t conditions = read_count(in);
        for (std::uint32_t j = 0; j < conditions; ++j) {
            MedicalCondition condition;
            condition.condition_id = read_string(in);
            condition.severity = read_double(in);
            condition.recovery_per_day = read_double(in);
            condition.work_capacity_at_full_severity = read_double(in);
            const std::uint8_t lasting = read_u8(in);
            if (lasting > 1U) throw std::runtime_error("invalid lasting-impairment flag");
            condition.lasting_impairment = lasting != 0U;
            condition.impairment_floor = read_double(in);
            condition.care_hours_per_severity = read_double(in);
            character.conditions.push_back(std::move(condition));
        }
        const std::uint32_t treatments = read_count(in);
        for (std::uint32_t j = 0; j < treatments; ++j) {
            MedicalTreatment treatment;
            treatment.treatment_id = read_string(in);
            treatment.condition_id = read_string(in);
            treatment.effectiveness = read_double(in);
            treatment.daily_cost = read_double(in);
            treatment.complication_risk = read_double(in);
            const std::uint8_t active = read_u8(in);
            if (active > 1U) throw std::runtime_error("invalid treatment-active flag");
            treatment.active = active != 0U;
            character.treatments.push_back(std::move(treatment));
        }
        character.care_need_hours = read_double(in);
        character.lost_income = read_double(in);
        character.missed_work_days = read_u32(in);
        const std::uint32_t personality = read_count(in);
        for (std::uint32_t j = 0; j < personality; ++j) {
            const std::string target = read_string(in);
            if (!character.personality.emplace(target, read_double(in)).second)
                throw std::runtime_error("duplicate life personality entry");
        }
        const std::uint32_t memories = read_count(in);
        for (std::uint32_t j = 0; j < memories; ++j) {
            const std::string target = read_string(in);
            if (!character.memories.emplace(target, read_double(in)).second)
                throw std::runtime_error("duplicate life memory entry");
        }
        const EntityId id = character.entity_id;
        if (id.empty() || !characters.emplace(id, std::move(character)).second)
            throw std::runtime_error("duplicate or empty life character id");
    }
    std::vector<LifeObligation> obligations;
    const std::uint32_t obligation_count = read_count(in);
    obligations.reserve(obligation_count);
    for (std::uint32_t i = 0; i < obligation_count; ++i) {
        LifeObligation obligation;
        obligation.obligation_id = read_string(in);
        obligation.debtor_id = read_string(in);
        obligation.creditor_id = read_string(in);
        obligation.amount_due = read_double(in);
        obligation.due_day = read_u64(in);
        const std::uint8_t settled = read_u8(in);
        const std::uint8_t missed = read_u8(in);
        if (settled > 1U || missed > 1U) throw std::runtime_error("invalid obligation flags");
        obligation.settled = settled != 0U;
        obligation.missed = missed != 0U;
        obligations.push_back(std::move(obligation));
    }
    std::vector<GhostTimeWindow> windows;
    const std::uint32_t window_count = read_count(in);
    windows.reserve(window_count);
    for (std::uint32_t i = 0; i < window_count; ++i) {
        GhostTimeWindow window{read_double(in), read_double(in), read_double(in)};
        if (version >= 7U) {
            const std::uint32_t action_count = read_count(in);
            window.permitted_actions.clear();
            window.permitted_actions.reserve(action_count);
            for (std::uint32_t j = 0; j < action_count; ++j)
                window.permitted_actions.push_back(read_string(in));
        }
        windows.push_back(std::move(window));
    }
    life.restore_snapshot(std::move(characters), std::move(obligations), std::move(windows));
}

void write_information_claim(std::ostream& out, const InformationClaim& claim) {
    write_string(out, claim.claim_id);
    write_string(out, claim.subject_key);
    write_string(out, claim.proposition_key);
    write_string(out, claim.root_evidence_id);
    write_string(out, claim.parent_claim_id);
    write_string(out, claim.source_entity_id);
    write_string(out, claim.recipient_entity_id);
    write_u64(out, static_cast<std::uint64_t>(claim.created_tick));
    write_double(out, claim.confidence);
    write_u32(out, claim.hop_count);
    write_u8(out, static_cast<std::uint8_t>(claim.kind));
}

InformationClaim read_information_claim(std::istream& in) {
    InformationClaim claim;
    claim.claim_id = read_string(in);
    claim.subject_key = read_string(in);
    claim.proposition_key = read_string(in);
    claim.root_evidence_id = read_string(in);
    claim.parent_claim_id = read_string(in);
    claim.source_entity_id = read_string(in);
    claim.recipient_entity_id = read_string(in);
    const std::uint64_t tick = read_u64(in);
    if (tick > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        throw std::runtime_error("information claim tick exceeds supported range");
    claim.created_tick = static_cast<std::int64_t>(tick);
    claim.confidence = read_double(in);
    claim.hop_count = read_u32(in);
    claim.kind = read_enum<InformationKind>(in, 3U, "information kind");
    return claim;
}

void write_information_ledger(std::ostream& out, const InformationLedger& ledger) {
    std::vector<InformationClaim> ordered;
    ordered.reserve(ledger.size());
    for (const auto& [id, claim] : ledger.claims()) {
        (void)id;
        ordered.push_back(claim);
    }
    // Parents have smaller hop counts than descendants. Stable sorting restores
    // claims in parent-first order and keeps snapshot bytes deterministic.
    std::sort(ordered.begin(), ordered.end(),
        [](const InformationClaim& left, const InformationClaim& right) {
            if (left.hop_count != right.hop_count) return left.hop_count < right.hop_count;
            return left.claim_id < right.claim_id;
        });
    write_count(out, ordered.size());
    for (const InformationClaim& claim : ordered) write_information_claim(out, claim);
}

void read_information_ledger(std::istream& in, InformationLedger& ledger) {
    const std::uint32_t count = read_count(in);
    for (std::uint32_t i = 0; i < count; ++i) {
        const InformationClaim claim = read_information_claim(in);
        const ClaimResult result = ledger.record(claim);
        if (!result.accepted)
            throw std::runtime_error("invalid information ledger snapshot claim: " + result.error);
    }
}

} // namespace

void save_world(const SimulationWorld& world, std::ostream& output) {
    output.write(kMagicV12.data(), static_cast<std::streamsize>(kMagicV12.size()));
    if (!output) throw std::runtime_error("failed writing world snapshot header");
    write_u32(output, kWorldSaveVersion);
    write_double(output, world.total_hours());
    write_u64(output, world.random_state());
    write_world_state(output, world.state());
    write_count(output, world.fixer_networks().size());
    for (const FixerNetwork& network : world.fixer_networks()) write_network(output, network);
    write_life_state(output, world.life_system());
    write_information_ledger(output, world.information_ledger());
}

SimulationWorld load_world(std::istream& input) {
    std::array<char, kMagicV8.size()> magic{};
    input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
    if (!input) throw std::runtime_error("truncated world snapshot header");
    const bool is_v5 = magic == kMagicV5;
    const bool is_v6 = magic == kMagicV6;
    const bool is_v7 = magic == kMagicV7;
    const bool is_v8 = magic == kMagicV8;
    const bool is_v9 = magic == kMagicV9;
    const bool is_v10 = magic == kMagicV10;
    const bool is_v11 = magic == kMagicV11;
    const bool is_v12 = magic == kMagicV12;
    if (!is_v5 && !is_v6 && !is_v7 && !is_v8 && !is_v9 && !is_v10 && !is_v11 && !is_v12) throw std::runtime_error("invalid world snapshot magic");
    const std::uint32_t version = read_u32(input);
    if ((version == 5U && !is_v5) || (version == 6U && !is_v6)
        || (version == 7U && !is_v7) || (version == 8U && !is_v8)
        || (version == 9U && !is_v9) || (version == 10U && !is_v10)
        || (version == 11U && !is_v11) || (version == 12U && !is_v12)
        || (version != 5U && version != 6U && version != 7U && version != 8U
            && version != 9U && version != 10U && version != 11U && version != 12U)) {
        throw std::runtime_error("unsupported world snapshot version");
    }

    const double total_hours = read_double(input);
    if (total_hours < 0.0) throw std::runtime_error("snapshot has negative simulation time");
    const std::uint64_t random_state = read_u64(input);
    WorldState state = read_world_state(input, version);
    const std::uint32_t networks = read_count(input);
    std::vector<FixerNetwork> fixer_networks;
    fixer_networks.reserve(networks);
    for (std::uint32_t i = 0; i < networks; ++i) {
        fixer_networks.push_back(read_network(input));
    }

    SimulationWorld world(std::move(state), total_hours, random_state);
    world.fixer_networks() = std::move(fixer_networks);
    if (version >= 6U) read_life_state(input, world.life_system(), version);
    if (version >= 11U) read_information_ledger(input, world.information_ledger());
    return world;
}

} // namespace simreality

#include "simreality/WorldPersistence.h"

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

namespace simreality {
namespace {
constexpr std::array<char, 8> kMagic{{'S', 'R', 'E', 'C', 'O', 'R', 'E', '5'}};
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
    value.action_tag = read_enum<ActionTag>(in, 4U, "action tag");
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
}

NPC read_npc(std::istream& in) {
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

WorldState read_world_state(std::istream& in) {
    WorldState value;
    const std::uint32_t npcs = read_count(in);
    value.npcs.reserve(npcs);
    for (std::uint32_t i = 0; i < npcs; ++i) value.npcs.push_back(read_npc(in));
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
        event.action_tag = read_enum<ActionTag>(in, 4U, "event action");
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

} // namespace

void save_world(const SimulationWorld& world, std::ostream& output) {
    output.write(kMagic.data(), static_cast<std::streamsize>(kMagic.size()));
    if (!output) throw std::runtime_error("failed writing world snapshot header");
    write_u32(output, kWorldSaveVersion);
    write_double(output, world.total_hours());
    write_u64(output, world.random_state());
    write_world_state(output, world.state());
    write_count(output, world.fixer_networks().size());
    for (const FixerNetwork& network : world.fixer_networks()) write_network(output, network);
}

SimulationWorld load_world(std::istream& input) {
    std::array<char, kMagic.size()> magic{};
    input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
    if (!input) throw std::runtime_error("truncated world snapshot header");
    if (magic != kMagic) throw std::runtime_error("invalid world snapshot magic");
    const std::uint32_t version = read_u32(input);
    if (version != kWorldSaveVersion) {
        throw std::runtime_error("unsupported world snapshot version");
    }

    const double total_hours = read_double(input);
    if (total_hours < 0.0) throw std::runtime_error("snapshot has negative simulation time");
    const std::uint64_t random_state = read_u64(input);
    WorldState state = read_world_state(input);
    const std::uint32_t networks = read_count(input);
    std::vector<FixerNetwork> fixer_networks;
    fixer_networks.reserve(networks);
    for (std::uint32_t i = 0; i < networks; ++i) {
        fixer_networks.push_back(read_network(input));
    }

    SimulationWorld world(std::move(state), total_hours, random_state);
    world.fixer_networks() = std::move(fixer_networks);
    return world;
}

} // namespace simreality

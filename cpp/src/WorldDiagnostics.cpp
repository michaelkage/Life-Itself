#include "simreality/WorldDiagnostics.h"

#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace simreality {

WorldMetrics collect_world_metrics(const WorldState& state) {
    WorldMetrics metrics;
    metrics.residents = state.npcs.size();
    for (const NPC& npc : state.npcs) {
        if (!npc.home_id.empty()) ++metrics.housed_residents;
        if (!npc.job_id.empty()) ++metrics.employed_residents;
        metrics.resident_cash += npc.money;
        metrics.average_stress += std::clamp(npc.personal_stress, 0.0, 1.0);
        metrics.average_isolation += std::clamp(npc.isolation, 0.0, 1.0);
        metrics.average_social_need += std::clamp(npc.social_need, 0.0, 1.0);
    }
    if (!state.npcs.empty()) {
        const double count = static_cast<double>(state.npcs.size());
        metrics.average_stress /= count;
        metrics.average_isolation /= count;
        metrics.average_social_need /= count;
    }
    for (const Business& business : state.businesses) {
        if (business.open) ++metrics.open_businesses;
        metrics.business_cash += business.cash;
        metrics.available_business_stock += business.stock;
    }
    for (const OngoingEvent& event : state.ongoing_events)
        if (!event.resolved) ++metrics.unresolved_events;
    return metrics;
}

WorldInvariantReport validate_world_state(const WorldState& state) {
    WorldInvariantReport report;
    const auto violation = [&report](std::string message) {
        report.violations.push_back(std::move(message));
    };
    const auto in_unit_interval = [](double value) {
        return std::isfinite(value) && value >= 0.0 && value <= 1.0;
    };
    std::unordered_set<EntityId> npc_ids;
    std::unordered_set<DistrictId> district_ids;
    std::unordered_set<EntityId> housing_ids;
    std::unordered_set<EntityId> business_ids;

    for (const District& district : state.districts) {
        if (district.district_id.empty()) violation("district has an empty id");
        if (!district_ids.insert(district.district_id).second) violation("duplicate district id: " + district.district_id);
        if (!in_unit_interval(district.overpopulation)) violation("district overpopulation outside [0,1]: " + district.district_id);
        if (!in_unit_interval(district.supply_shortage)) violation("district supply shortage outside [0,1]: " + district.district_id);
        if (!in_unit_interval(district.transport_reliability)) violation("district transport reliability outside [0,1]: " + district.district_id);
        if (!in_unit_interval(district.service_capacity)) violation("district service capacity outside [0,1]: " + district.district_id);
    }
    for (const HousingUnit& unit : state.housing_units) {
        if (unit.unit_id.empty()) violation("housing unit has an empty id");
        if (!housing_ids.insert(unit.unit_id).second) violation("duplicate housing id: " + unit.unit_id);
        if (!std::isfinite(unit.daily_rent) || unit.daily_rent < 0.0) violation("invalid housing rent: " + unit.unit_id);
        if (district_ids.find(unit.district_id) == district_ids.end()) violation("housing references missing district: " + unit.unit_id);
    }
    for (const Business& business : state.businesses) {
        if (business.business_id.empty()) violation("business has an empty id");
        if (!business_ids.insert(business.business_id).second) violation("duplicate business id: " + business.business_id);
        if (!std::isfinite(business.cash) || business.cash < 0.0) violation("invalid business cash: " + business.business_id);
        if (!std::isfinite(business.stock) || business.stock < 0.0 || business.stock > std::max(0.0, business.stock_capacity))
            violation("business stock outside capacity: " + business.business_id);
        if (district_ids.find(business.district_id) == district_ids.end()) violation("business references missing district: " + business.business_id);
    }
    std::unordered_map<EntityId, std::size_t> occupancy;
    for (const NPC& npc : state.npcs) {
        if (npc.entity_id.empty()) violation("NPC has an empty id");
        if (!npc_ids.insert(npc.entity_id).second) violation("duplicate NPC id: " + npc.entity_id);
        if (!std::isfinite(npc.money) || npc.money < 0.0) violation("invalid resident money: " + npc.entity_id);
        if (!in_unit_interval(npc.personal_stress)) violation("resident stress outside [0,1]: " + npc.entity_id);
        if (!in_unit_interval(npc.social_need)) violation("resident social need outside [0,1]: " + npc.entity_id);
        if (!in_unit_interval(npc.isolation)) violation("resident isolation outside [0,1]: " + npc.entity_id);
        if (!npc.district_id.empty() && district_ids.find(npc.district_id) == district_ids.end())
            violation("resident references missing district: " + npc.entity_id);
        if (!npc.home_id.empty()) {
            if (housing_ids.find(npc.home_id) == housing_ids.end()) violation("resident references missing home: " + npc.entity_id);
            ++occupancy[npc.home_id];
        }
        // Empty or unmatched job IDs are permitted for legacy jobs without Business records.
        for (const auto& [other_id, strength] : npc.relationships) {
            if (!std::isfinite(strength) || strength < -1.0 || strength > 1.0)
                violation("relationship strength outside [-1,1]: " + npc.entity_id + " -> " + other_id);
        }
    }
    for (const auto& [unit_id, count] : occupancy) {
        const auto unit = std::find_if(state.housing_units.begin(), state.housing_units.end(),
            [&unit_id](const HousingUnit& candidate) { return candidate.unit_id == unit_id; });
        if (unit != state.housing_units.end() && count > unit->capacity)
            violation("housing capacity exceeded: " + unit_id);
    }
    for (const OngoingEvent& event : state.ongoing_events) {
        if (!in_unit_interval(event.investigation_progress))
            violation("investigation progress outside [0,1]: " + event.event_id);
    }
    return report;
}

} // namespace simreality

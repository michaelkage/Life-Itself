#include "simreality/SimulationWorld.h"

#include "simreality/Decay.h"
#include "simreality/DecisionSystem.h"
#include "simreality/Districts.h"
#include "simreality/Ecosystem.h"
#include "simreality/Gossip.h"
#include "simreality/Trauma.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace simreality {

SimulationWorld::SimulationWorld(
    WorldState initial_state, double initial_hour, std::uint64_t random_seed)
    : state_(std::move(initial_state)),
      runtime_(initial_hour),
      random_(random_seed) {}

GhostInfluenceResult SimulationWorld::attempt_ghost_influence(
    const EntityId& ghost_id, const EntityId& npc_id,
    const std::string& action, double hour_of_day) {
    const GhostInfluenceResult result = life_.attempt_ghost_influence(
        ghost_id, npc_id, action, hour_of_day, state_, random_.next_u64());
    if (!result.accepted) return result;

    // Accepted ghost actions become part of the same event stream as other
    // witnessed interactions, while remaining resolved social events rather
    // than entering the criminal-investigation path.
    NPC* witness = nullptr;
    for (NPC& candidate : state_.npcs) {
        if (candidate.entity_id == npc_id) {
            witness = &candidate;
            break;
        }
    }
    if (witness == nullptr) return result;

    const double day_start = std::floor(runtime_.total_hours() / 24.0) * 24.0;
    const double event_hour = day_start + hour_of_day;
    // LifeCoordinator receives a clock-hour for window gating; memory decay and
    // replay require the absolute hour on the world's timeline.
    const ActionTag manifestation_tag = action == "sign" ? ActionTag::GhostSign
        : (action == "sound" ? ActionTag::GhostSound : ActionTag::GhostDream);
    for (NPCMemory& memory : witness->memories) {
        if (memory.target_entity_id == ghost_id && memory.action_tag == manifestation_tag) {
            memory.timestamp_hour = event_hour;
            break;
        }
    }
    const auto hour_key = static_cast<std::uint64_t>(std::llround(event_hour * 1000.0));
    OngoingEvent event;
    event.event_id = "ghost-influence:" + ghost_id + ":" + npc_id + ":"
        + action + ":" + std::to_string(hour_key) + ":"
        + std::to_string(state_.ongoing_events.size());
    event.district_id = witness->district_id;
    event.actor_id = ghost_id;
    event.action_tag = action == "sign" ? ActionTag::GhostSign
        : (action == "sound" ? ActionTag::GhostSound : ActionTag::GhostDream);
    event.created_hour = event_hour;
    event.severity = result.score;
    event.witness_ids.push_back(npc_id);
    event.resolved = true;
    state_.ongoing_events.push_back(std::move(event));

    // Different manifestations leave different social traces in the witness.
    // Memory reinforcement is applied by LifeCoordinator before these effects.
    if (action == "sound") {
        witness->personal_stress = std::clamp(
            witness->personal_stress + 0.03 * result.score, 0.0, 1.0);
    } else if (action == "dream") {
        witness->isolation = std::max(0.0, witness->isolation - 0.02 * result.score);
        witness->social_need = std::max(0.0, witness->social_need - 0.015 * result.score);
    } else if (action == "sign") {
        double& tie = witness->relationships[ghost_id];
        tie = std::clamp(tie + 0.02 * result.score, -1.0, 1.0);
    }
    return result;
}

WorldAdvanceReport SimulationWorld::advance(
    double elapsed_hours, Weather visibility_weather, double weather_severity) {
    WorldAdvanceReport report;
    report.ticks = runtime_.advance(elapsed_hours);

    for (const ScheduledTick& tick : report.ticks) {
        const auto hour = static_cast<std::uint8_t>(
            static_cast<std::uint64_t>(tick.at_hour) % 24U);
        for (NPC& npc : state_.npcs) {
            bool matched_schedule = false;
            for (const ScheduleEntry& entry : npc.schedule) {
                const bool in_window = entry.start_hour <= entry.end_hour
                    ? hour >= entry.start_hour && hour < entry.end_hour
                    : hour >= entry.start_hour || hour < entry.end_hour;
                if (in_window) {
                    npc.current_activity = entry.activity;
                    matched_schedule = true;
                    break;
                }
            }
            if (!matched_schedule) {
                const auto decision_district = std::find_if(
                    state_.districts.begin(), state_.districts.end(),
                    [&npc](const District& candidate) { return candidate.district_id == npc.district_id; });
                const bool has_open_shop = std::any_of(
                    state_.businesses.begin(), state_.businesses.end(),
                    [&npc](const Business& business) {
                        return business.district_id == npc.district_id && business.open && business.stock > 0.0;
                    });
                const bool trusted_contact = std::any_of(
                    npc.relationships.begin(), npc.relationships.end(),
                    [this, &npc](const auto& relationship) {
                        if (relationship.second < 0.25) return false;
                        return std::any_of(state_.npcs.begin(), state_.npcs.end(),
                            [&npc, &relationship](const NPC& other) {
                                return other.entity_id == relationship.first
                                    && other.district_id == npc.district_id
                                    && other.entity_id != npc.entity_id;
                            });
                    });
                const ActivityContext context{
                    hour,
                    has_open_shop,
                    decision_district != state_.districts.end()
                        && decision_district->service_capacity > 0.2,
                    trusted_contact};
                npc.current_activity = choose_activity(
                    npc, decision_district == state_.districts.end() ? nullptr : &*decision_district,
                    context).activity;
            }
            const auto district = std::find_if(state_.districts.begin(), state_.districts.end(),
                [&npc](const District& candidate) { return candidate.district_id == npc.district_id; });
            if (district != state_.districts.end() && npc.current_activity == DailyActivity::Commute
                && district->transport_reliability < 0.3) {
                npc.current_activity = DailyActivity::Home;
                npc.commute_disrupted_today = true;
                npc.personal_stress = std::clamp(npc.personal_stress
                    + (0.3 - district->transport_reliability) * 0.2, 0.0, 1.0);
            }
            if (npc.current_activity == DailyActivity::Work && !npc.commute_disrupted_today)
                npc.work_hours_today = std::min(8.0, npc.work_hours_today + 1.0);
        }
        if (tick.kind == TickKind::Hourly) {
            // Schedules drive hourly economic and social behaviour, not just a label.
            for (NPC& npc : state_.npcs) {
                npc.memories = sweep(
                    npc.memories, npc.age_band, tick.at_hour, visibility_weather);
                report.memories_swept += npc.memories.size();
                const auto district = std::find_if(state_.districts.begin(), state_.districts.end(),
                    [&npc](const District& candidate) { return candidate.district_id == npc.district_id; });
                if (district == state_.districts.end()) continue;
                if (npc.current_activity == DailyActivity::Shop && npc.money > 0.0) {
                    auto shop = std::find_if(state_.businesses.begin(), state_.businesses.end(),
                        [&npc](const Business& business) {
                            return business.district_id == npc.district_id && business.open && business.stock > 0.0;
                        });
                    if (shop != state_.businesses.end()) {
                        const double purchase = std::min({npc.money, 5.0, shop->stock});
                        npc.money -= purchase;
                        shop->stock -= purchase;
                        shop->cash += purchase;
                        district->shop_stock = std::max(0.0, district->shop_stock - purchase * 0.01);
                    }
                } else if (npc.current_activity == DailyActivity::Service
                    && district->service_capacity > 0.0) {
                    const double access = std::clamp(district->service_capacity, 0.0, 1.0);
                    npc.personal_stress = std::clamp(npc.personal_stress - 0.02 * access, 0.0, 1.0);
                    npc.desperation_index = std::clamp(npc.desperation_index - 0.01 * access, 0.0, 1.0);
                    npc.social_need = std::clamp(npc.social_need - 0.015 * access, 0.0, 1.0);
                }
            }
            // Shared social time creates reciprocal ties and support over repeated encounters.
            for (std::size_t i = 0; i < state_.npcs.size(); ++i) {
                NPC& first = state_.npcs[i];
                if (first.current_activity != DailyActivity::Socialise) continue;
                for (std::size_t j = i + 1; j < state_.npcs.size(); ++j) {
                    NPC& second = state_.npcs[j];
                    if (second.current_activity != DailyActivity::Socialise
                        || first.district_id != second.district_id) continue;
                    double& first_tie = first.relationships[second.entity_id];
                    double& second_tie = second.relationships[first.entity_id];
                    first_tie = std::clamp(first_tie + 0.015, -1.0, 1.0);
                    second_tie = std::clamp(second_tie + 0.015, -1.0, 1.0);
                    first.social_need = std::max(0.0, first.social_need - 0.05);
                    second.social_need = std::max(0.0, second.social_need - 0.05);
                    first.isolation = std::max(0.0, first.isolation - 0.04);
                    second.isolation = std::max(0.0, second.isolation - 0.04);
                    first.personal_stress = std::max(0.0, first.personal_stress - 0.005);
                    second.personal_stress = std::max(0.0, second.personal_stress - 0.005);
                }
            }
            continue;
        }

        for (const NPC& npc : state_.npcs) {
            if (!life_.characters().contains(npc.entity_id)) life_.register_character(npc.entity_id);
        }
        life_.advance_day(state_, tick.day_index);
        for (District& district : state_.districts) {
            DistrictDayResult district_result;
            district_result.district_id = district.district_id;
            district_result.scars = tick_day(district, weather_severity);
            for (OngoingEvent& event : state_.ongoing_events) {
                if (event.district_id != district.district_id || event.resolved) continue;
                std::size_t actionable_witnesses = 0;
                for (const EntityId& witness_id : event.witness_ids) {
                    const auto witness = std::find_if(state_.npcs.begin(), state_.npcs.end(),
                        [&witness_id](const NPC& candidate) { return candidate.entity_id == witness_id; });
                    if (witness == state_.npcs.end()) continue;
                    const bool has_actionable_memory = std::any_of(
                        witness->memories.begin(), witness->memories.end(),
                        [&event](const NPCMemory& memory) {
                            return memory.target_entity_id == event.actor_id
                                && memory.action_tag == event.action_tag
                                && memory.is_actionable();
                        });
                    if (has_actionable_memory) ++actionable_witnesses;
                }
                if (actionable_witnesses > 0U) {
                    const double evidence = std::min(1.0,
                        static_cast<double>(actionable_witnesses) / 2.0);
                    const double local_response = district.security_presence
                        * (1.0 - district.local_corruption);
                    event.investigation_progress = std::clamp(
                        event.investigation_progress + 0.1 * evidence * local_response,
                        0.0, 1.0);
                    if (event.investigation_progress >= 1.0) event.resolved = true;
                }
            }
            // Housing occupancy is capacity-constrained and move-ins require an affordable rent buffer.
            std::size_t total_housing_slots = 0;
            for (const HousingUnit& unit : state_.housing_units)
                if (unit.district_id == district.district_id) total_housing_slots += unit.capacity;
            for (NPC& resident : state_.npcs) {
                if (resident.district_id != district.district_id || !resident.home_id.empty()) continue;
                const HousingUnit* selected_unit = nullptr;
                std::size_t selected_occupancy = 0;
                double selected_trust = -1.0;
                for (const HousingUnit& unit : state_.housing_units) {
                    if (unit.district_id != district.district_id || unit.capacity == 0U) continue;
                    std::size_t occupied = 0;
                    double best_housemate_trust = -1.0;
                    for (const NPC& other : state_.npcs) {
                        if (other.district_id != district.district_id || other.home_id != unit.unit_id) continue;
                        ++occupied;
                        const auto forward = resident.relationships.find(other.entity_id);
                        const auto reverse = other.relationships.find(resident.entity_id);
                        const double trust = std::min(
                            forward == resident.relationships.end() ? 0.0 : forward->second,
                            reverse == other.relationships.end() ? 0.0 : reverse->second);
                        best_housemate_trust = std::max(best_housemate_trust, trust);
                    }
                    if (occupied >= unit.capacity) continue;
                    const double rent = std::max(0.0, unit.daily_rent);
                    const bool can_afford_alone = occupied == 0U && resident.money >= rent * 3.0;
                    const bool can_share_with_trusted_person = occupied > 0U
                        && best_housemate_trust >= 0.5
                        && resident.money >= (rent / static_cast<double>(occupied + 1U)) * 3.0;
                    if (!can_afford_alone && !can_share_with_trusted_person) continue;
                    const double trust_score = occupied == 0U ? 0.0 : best_housemate_trust;
                    if (selected_unit == nullptr || trust_score > selected_trust) {
                        selected_unit = &unit;
                        selected_occupancy = occupied;
                        selected_trust = trust_score;
                    }
                }
                if (selected_unit != nullptr) {
                    resident.home_id = selected_unit->unit_id;
                    resident.daily_rent = std::max(0.0, selected_unit->daily_rent)
                        / static_cast<double>(selected_occupancy + 1U);
                    resident.rent_arrears = 0.0;
                    for (NPC& housemate : state_.npcs) {
                        if (housemate.entity_id == resident.entity_id
                            || housemate.home_id != selected_unit->unit_id) continue;
                        housemate.daily_rent = std::max(0.0, selected_unit->daily_rent)
                            / static_cast<double>(selected_occupancy + 1U);
                    }
                }
            }
            std::size_t vacant_housing_slots = 0;
            for (const HousingUnit& unit : state_.housing_units) {
                if (unit.district_id != district.district_id) continue;
                std::size_t occupied = 0;
                for (const NPC& resident : state_.npcs)
                    if (resident.district_id == district.district_id && resident.home_id == unit.unit_id) ++occupied;
                if (occupied < unit.capacity) vacant_housing_slots += unit.capacity - occupied;
            }
            if (total_housing_slots > 0U)
                district.housing_availability = static_cast<double>(vacant_housing_slots) / static_cast<double>(total_housing_slots);
            else
                district.housing_availability = std::any_of(state_.npcs.begin(), state_.npcs.end(),
                    [&district](const NPC& resident) { return resident.district_id == district.district_id && resident.home_id.empty(); })
                    ? 0.0 : 1.0;
            for (Business& business : state_.businesses) {
                if (business.district_id != district.district_id || !business.open) continue;
                business.stock = std::clamp(business.stock, 0.0, std::max(0.0, business.stock_capacity));
                business.cash = std::max(0.0, business.cash);
                const double delivery_capacity = std::max(0.0, district.service_capacity) * 20.0;
                const double wanted = std::min(std::max(0.0, business.stock_capacity - business.stock),
                    delivery_capacity * std::clamp(district.transport_reliability, 0.0, 1.0));
                const double affordable = business.restock_cost_per_unit > 0.0
                    ? business.cash / business.restock_cost_per_unit : wanted;
                const double delivered = std::min(wanted, affordable);
                business.stock += delivered;
                business.cash -= delivered * std::max(0.0, business.restock_cost_per_unit);
                std::size_t employed = 0;
                for (const NPC& resident : state_.npcs)
                    if (resident.district_id == district.district_id && resident.job_id == business.business_id) ++employed;
                while (employed < business.job_slots) {
                    NPC* candidate = nullptr;
                    double best_referral = -1.0;
                    for (NPC& resident : state_.npcs) {
                        if (resident.district_id != district.district_id || !resident.job_id.empty()) continue;
                        double referral = 0.0;
                        for (const NPC& employee : state_.npcs) {
                            if (employee.job_id != business.business_id || employee.district_id != district.district_id) continue;
                            const auto tie = employee.relationships.find(resident.entity_id);
                            const auto reciprocal = resident.relationships.find(employee.entity_id);
                            const double trust = std::min(
                                tie == employee.relationships.end() ? 0.0 : tie->second,
                                reciprocal == resident.relationships.end() ? 0.0 : reciprocal->second);
                            if (trust >= 0.5) referral = std::max(referral, trust);
                        }
                        if (candidate == nullptr || referral > best_referral) {
                            candidate = &resident;
                            best_referral = referral;
                        }
                    }
                    if (candidate == nullptr) break;
                    candidate->job_id = business.business_id;
                    candidate->hourly_wage = std::max(0.0, business.hourly_wage);
                    candidate->goals.erase(std::remove(candidate->goals.begin(), candidate->goals.end(), "find_work"),
                        candidate->goals.end());
                    ++employed;
                }
            }
            double payroll = 0.0;
            double rent_collected = 0.0;
            std::size_t resident_count = 0;
            for (NPC& resident : state_.npcs) {
                if (resident.district_id != district.district_id) continue;
                ++resident_count;
                if (!resident.job_id.empty()) {
                    const double expected_income = std::max(0.0, resident.hourly_wage) * 8.0;
                    const double attended_hours = resident.commute_disrupted_today ? 0.0
                        : std::clamp(resident.work_hours_today, 0.0, 8.0);
                    const double wage = std::max(0.0, resident.hourly_wage) * attended_hours;
                    double paid_income = 0.0;
                    auto employer = std::find_if(state_.businesses.begin(), state_.businesses.end(),
                        [&resident, &district](const Business& business) {
                            return business.business_id == resident.job_id
                                && business.district_id == district.district_id && business.open;
                        });
                    if (employer == state_.businesses.end()) {
                        resident.money += wage;
                        payroll += wage;
                        paid_income = wage;
                    } else if (employer->cash >= wage) {
                        employer->cash -= wage;
                        resident.money += wage;
                        payroll += wage;
                        paid_income = wage;
                    } else {
                        resident.job_id.clear();
                        resident.hourly_wage = 0.0;
                        if (std::find(resident.goals.begin(), resident.goals.end(), "find_work") == resident.goals.end())
                            resident.goals.push_back("find_work");
                    }
                    const double lost = std::max(0.0, expected_income - paid_income);
                    resident.lost_income += lost;
                    if (lost > 0.0) {
                        ++resident.missed_work_days;
                        resident.personal_stress = std::clamp(resident.personal_stress + 0.03, 0.0, 1.0);
                    }
                }
                // Trusted friends can bridge a temporary income shock before rent is collected.
                if (resident.lost_income > 0.0 || resident.money < std::max(1.0, resident.daily_rent * 2.0)) {
                    const double need = std::min(10.0, std::max(0.0, resident.daily_rent + resident.rent_arrears - resident.money));
                    if (need > 0.0) {
                        for (NPC& helper : state_.npcs) {
                            if (helper.entity_id == resident.entity_id || helper.district_id != district.district_id) continue;
                            const auto forward = resident.relationships.find(helper.entity_id);
                            const auto reverse = helper.relationships.find(resident.entity_id);
                            const double trust = std::min(
                                forward == resident.relationships.end() ? 0.0 : forward->second,
                                reverse == helper.relationships.end() ? 0.0 : reverse->second);
                            const double reserve = std::max(20.0, helper.daily_rent * 3.0);
                            if (trust < 0.5 || helper.money <= reserve) continue;
                            const double gift = std::min({need, helper.money - reserve, 10.0});
                            if (gift <= 0.0) continue;
                            helper.money -= gift;
                            resident.money += gift;
                            resident.personal_stress = std::clamp(resident.personal_stress - 0.04, 0.0, 1.0);
                            resident.desperation_index = std::clamp(resident.desperation_index - 0.05, 0.0, 1.0);
                            break;
                        }
                    }
                }
                const auto home = std::find_if(state_.housing_units.begin(), state_.housing_units.end(),
                    [&resident, &district](const HousingUnit& unit) {
                        return unit.unit_id == resident.home_id && unit.district_id == district.district_id;
                    });
                const double rent_due = std::max(0.0, resident.daily_rent);
                const double rent = std::min(std::max(0.0, resident.money), rent_due + resident.rent_arrears);
                resident.money -= rent;
                rent_collected += rent;
                resident.rent_arrears = std::max(0.0, resident.rent_arrears + rent_due - rent);
                if (rent_due > 0.0 && resident.rent_arrears >= rent_due * 3.0 && !resident.home_id.empty()) {
                    resident.home_id.clear();
                    resident.daily_rent = 0.0;
                    resident.personal_stress = std::clamp(resident.personal_stress + 0.15, 0.0, 1.0);
                    resident.desperation_index = std::clamp(resident.desperation_index + 0.2, 0.0, 1.0);
                    if (std::find(resident.goals.begin(), resident.goals.end(), "find_housing") == resident.goals.end())
                        resident.goals.push_back("find_housing");
                }
            }
            district.cash_circulation = std::max(0.0, district.cash_circulation + payroll - rent_collected);
            const double population_factor = std::min(1.0,
                static_cast<double>(resident_count) / static_cast<double>(std::max(1U, district.capacity)));
            district.supply_shortage = std::clamp(district.supply_shortage
                + population_factor * (1.0 - district.shop_stock) * 0.02
                - district.shop_stock * 0.005, 0.0, 1.0);
            district.employment_rate = std::clamp(district.employment_rate, 0.0, 1.0);
            district.housing_availability = std::clamp(district.housing_availability, 0.0, 1.0);
            district.transport_reliability = std::clamp(district.transport_reliability, 0.0, 1.0);
            district.service_capacity = std::clamp(district.service_capacity, 0.0, 1.0);
            for (FixerNetwork& network : fixer_networks_) {
                if (network.district_id == district.district_id) {
                    network.daily_update(district);
                }
            }

            for (NPC& npc : state_.npcs) {
                if (npc.district_id != district.district_id) continue;
                const BehaviourDecision behaviour = apply_district_pressure(npc, district);
                const auto ensure_goal = [&npc](const std::string& goal, bool needed) {
                    const auto found = std::find(npc.goals.begin(), npc.goals.end(), goal);
                    if (needed && found == npc.goals.end()) npc.goals.push_back(goal);
                    else if (!needed && found != npc.goals.end()) npc.goals.erase(found);
                };
                ensure_goal("find_housing", npc.home_id.empty());
                ensure_goal("find_work", npc.job_id.empty());
                ensure_goal("stabilise_finances",
                    npc.money < std::max(1.0, npc.daily_rent * 5.0));
                const double housing_pressure = npc.home_id.empty()
                    ? 0.25 * (1.0 - district.housing_availability) : 0.0;
                const double unemployment_pressure = npc.job_id.empty()
                    ? 0.15 * (1.0 - district.employment_rate) : 0.0;
                const double supply_pressure = 0.2 * district.supply_shortage;
                const double service_relief = npc.current_activity == DailyActivity::Service
                    ? 0.1 * district.service_capacity : 0.0;
                std::size_t household_contacts = 0;
                for (const NPC& other : state_.npcs) {
                    if (other.entity_id == npc.entity_id || other.district_id != npc.district_id) continue;
                    if (!npc.home_id.empty() && other.home_id == npc.home_id) ++household_contacts;
                }
                double trusted_ties = 0.0;
                for (const auto& [other_id, strength] : npc.relationships)
                    if (strength > 0.25) trusted_ties += strength;
                if (npc.current_activity == DailyActivity::Socialise) {
                    npc.social_need = std::max(0.0, npc.social_need - 0.12);
                    npc.isolation = std::max(0.0, npc.isolation - 0.08);
                } else {
                    npc.social_need = std::min(1.0, npc.social_need + 0.025);
                    npc.isolation = std::clamp(npc.isolation + (trusted_ties > 0.0 || household_contacts > 0U ? 0.005 : 0.035), 0.0, 1.0);
                }
                const double social_strain = npc.social_need * 0.04 + npc.isolation * 0.05;
                const double social_support = std::min(0.08, trusted_ties * 0.015 + static_cast<double>(household_contacts) * 0.02);
                // Financial and housing shocks hurt more when isolated; trusted ties and shared homes buffer them.
                const double isolation_multiplier = 1.0 + npc.isolation * 0.5;
                npc.desperation_index = std::clamp(npc.desperation_index
                    + (housing_pressure + unemployment_pressure) * isolation_multiplier
                    + supply_pressure * isolation_multiplier + social_strain - service_relief - social_support, 0.0, 1.0);
                npc.personal_stress = std::clamp(npc.personal_stress
                    + (housing_pressure * 0.2 + unemployment_pressure * 0.2) * isolation_multiplier
                    + supply_pressure * 0.1 * isolation_multiplier + social_strain
                    - service_relief * 0.2 - social_support, 0.0, 1.0);
                const TraumaAssessment trauma_result =
                    daily_update(npc, npc.desperation_index, 1.0);
                district_result.residents.push_back(
                    {npc.entity_id, behaviour, trauma_result});
                // Work attendance and commute disruption are daily inputs, not lifetime flags.
                npc.work_hours_today = 0.0;
                npc.commute_disrupted_today = false;
            }
            report.daily_results.push_back(std::move(district_result));
        }
    }
    return report;
}

NPC& SimulationWorld::find_npc(const EntityId& entity_id) {
    const auto found = std::find_if(state_.npcs.begin(), state_.npcs.end(),
        [&entity_id](const NPC& npc) { return npc.entity_id == entity_id; });
    if (found == state_.npcs.end()) {
        throw std::out_of_range("NPC entity id not found: " + entity_id);
    }
    return *found;
}

const NPC& SimulationWorld::find_npc(const EntityId& entity_id) const {
    const auto found = std::find_if(state_.npcs.begin(), state_.npcs.end(),
        [&entity_id](const NPC& npc) { return npc.entity_id == entity_id; });
    if (found == state_.npcs.end()) {
        throw std::out_of_range("NPC entity id not found: " + entity_id);
    }
    return *found;
}

Conversation SimulationWorld::talk(
    const EntityId& listener_id, const EntityId& speaker_id) {
    NPC& listener = find_npc(listener_id);
    NPC& speaker = find_npc(speaker_id);
    if (listener.district_id != speaker.district_id) {
        throw std::invalid_argument("NPCs must share a district to converse");
    }
    const auto prior_listener_tie = listener.relationships.find(speaker_id);
    const auto prior_speaker_tie = speaker.relationships.find(listener_id);
    const double prior_trust = std::min(
        prior_listener_tie == listener.relationships.end() ? 0.0 : prior_listener_tie->second,
        prior_speaker_tie == speaker.relationships.end() ? 0.0 : prior_speaker_tie->second);
    const std::vector<NPCMemory> memories_before_conversation = listener.memories;
    Conversation conversation = converse(listener, speaker, listener.district_id);
    // Trust changes the quality of what travels: trusted sources reinforce a memory;
    // hostile or unreliable sources leave weaker, less certain impressions.
    const auto action_name = [](ActionTag tag) {
        switch (tag) {
            case ActionTag::InteractionPolite: return std::string("Interaction.Polite");
            case ActionTag::GhostSign: return std::string("Ghost.Sign");
            case ActionTag::GhostSound: return std::string("Ghost.Sound");
            case ActionTag::GhostDream: return std::string("Ghost.Dream");
            case ActionTag::CrimeTheft: return std::string("Crime.Theft");
            case ActionTag::CrimeAssault: return std::string("Crime.Assault");
            case ActionTag::CrimeArmedAssault: return std::string("Crime.ArmedAssault");
            case ActionTag::CrimeVandalism: return std::string("Crime.Vandalism");
        }
        return std::string("Unknown");
    };
    for (const Rumour& rumour : conversation.transferred) {
        const std::string expected_action = rumour.action_tag;
        const bool ghost_manifestation = expected_action == "Ghost.Sign"
            || expected_action == "Ghost.Sound" || expected_action == "Ghost.Dream";
        const bool already_knew_manifestation = ghost_manifestation
            && std::any_of(memories_before_conversation.begin(), memories_before_conversation.end(),
                [&rumour, &action_name, &expected_action](const NPCMemory& prior) {
                    return prior.target_entity_id == rumour.target_entity_id
                        && action_name(prior.action_tag) == expected_action;
                });
        if (ghost_manifestation && !already_knew_manifestation) {
            // The saved memory is the durable gate against repeating the reaction.
            if (expected_action == "Ghost.Sound") {
                listener.personal_stress = std::clamp(listener.personal_stress + 0.025, 0.0, 1.0);
            } else if (expected_action == "Ghost.Dream") {
                listener.isolation = std::max(0.0, listener.isolation - 0.02);
                listener.social_need = std::max(0.0, listener.social_need - 0.015);
            } else {
                double& tie = listener.relationships[rumour.target_entity_id];
                tie = std::clamp(tie + 0.02, -1.0, 1.0);
            }
        }
        for (NPCMemory& received : listener.memories) {
            if (received.target_entity_id != rumour.target_entity_id
                || action_name(received.action_tag) != expected_action) continue;
            if (prior_trust >= 0.5) {
                received.retention = std::clamp(received.retention + 0.05, 0.0, 1.0);
                received.initial_impact = std::max(received.initial_impact, received.retention);
                received.description.observations = std::min<std::uint32_t>(
                    received.description.observations + 1U, 1000000U);
            } else if (prior_trust < 0.0) {
                received.retention *= 0.65;
                received.initial_impact = std::min(received.initial_impact, received.retention);
                received.description.height_uncertainty_m += 0.15;
                for (auto& [colour, weight] : received.description.jacket_colour_weights) {
                    (void)colour;
                    weight *= 0.7;
                }
            }
        }
    }
    const double change = conversation.transferred.empty() ? 0.02
        : (prior_trust >= 0.5 ? 0.005 : (prior_trust < 0.0 ? -0.02 : -0.01));
    auto& listener_tie = listener.relationships[speaker_id];
    auto& speaker_tie = speaker.relationships[listener_id];
    listener_tie = std::clamp(listener_tie + change, -1.0, 1.0);
    speaker_tie = std::clamp(speaker_tie + change, -1.0, 1.0);
    // Contact meets social needs; damaging rumours can erode trust and raise strain.
    listener.social_need = std::clamp(listener.social_need - 0.12, 0.0, 1.0);
    speaker.social_need = std::clamp(speaker.social_need - 0.08, 0.0, 1.0);
    listener.isolation = std::clamp(listener.isolation - 0.1, 0.0, 1.0);
    speaker.isolation = std::clamp(speaker.isolation - 0.08, 0.0, 1.0);
    if (!conversation.transferred.empty()) {
        listener.personal_stress = std::clamp(listener.personal_stress + 0.01, 0.0, 1.0);
        speaker.personal_stress = std::clamp(speaker.personal_stress + 0.01, 0.0, 1.0);
    }
    return conversation;
}

std::size_t SimulationWorld::record_witnessed_action(
    const EntityId& actor_id, ActionTag action_tag, Description description,
    const std::vector<EntityId>& witness_ids, const EntityId& victim_id) {
    const NPC& actor = find_npc(actor_id);
    std::vector<NPC*> witnesses;
    std::vector<EntityId> processed;
    processed.reserve(witness_ids.size());
    witnesses.reserve(witness_ids.size());

    for (const EntityId& witness_id : witness_ids) {
        if (std::find(processed.begin(), processed.end(), witness_id) != processed.end()) {
            continue;
        }
        processed.push_back(witness_id);
        NPC& witness = find_npc(witness_id);
        if (witness_id == actor_id) {
            throw std::invalid_argument("an actor cannot be listed as a witness to their own action");
        }
        if (witness.district_id != actor.district_id) {
            throw std::invalid_argument("witness and actor must share a district");
        }
        witnesses.push_back(&witness);
    }

    NPC* victim = nullptr;
    if (!victim_id.empty()) {
        victim = &find_npc(victim_id);
        if (victim->district_id != actor.district_id) {
            throw std::invalid_argument("victim and actor must share a district");
        }
    }

    for (NPC* witness : witnesses) {
        NPCMemory memory;
        memory.witness_id = witness->entity_id;
        memory.target_entity_id = actor_id;
        memory.initial_impact = 1.0;
        memory.retention = 1.0;
        memory.timestamp_hour = runtime_.total_hours();
        memory.action_tag = action_tag;
        memory.description = description;
        witness->memories.push_back(std::move(memory));
        (void)absorb(*witness, action_tag, witness->entity_id == victim_id);
    }

    if (victim != nullptr &&
        std::find(processed.begin(), processed.end(), victim_id) == processed.end()) {
        (void)absorb(*victim, action_tag, true);
    }

    OngoingEvent event;
    event.event_id = "event-" + std::to_string(state_.ongoing_events.size() + 1U);
    event.district_id = actor.district_id;
    event.actor_id = actor_id;
    event.action_tag = action_tag;
    event.created_hour = runtime_.total_hours();
    switch (action_tag) {
        case ActionTag::InteractionPolite: event.severity = 0.05; break;
        case ActionTag::GhostSign:
        case ActionTag::GhostSound:
        case ActionTag::GhostDream: event.severity = 0.0; break;
        case ActionTag::CrimeTheft: event.severity = 0.4; break;
        case ActionTag::CrimeVandalism: event.severity = 0.45; break;
        case ActionTag::CrimeAssault: event.severity = 0.7; break;
        case ActionTag::CrimeArmedAssault: event.severity = 1.0; break;
    }
    for (const NPC* witness : witnesses) event.witness_ids.push_back(witness->entity_id);
    state_.ongoing_events.push_back(std::move(event));
    return witnesses.size();
}

CriminalFile SimulationWorld::build_criminal_file(const EntityId& player_id) const {
    std::vector<NPCMemory> memories;
    for (const NPC& npc : state_.npcs) {
        memories.insert(memories.end(), npc.memories.begin(), npc.memories.end());
    }
    return file_from_memories(player_id, memories);
}

ReputationProfile SimulationWorld::reputation_in_district(
    const DistrictId& district_id, const EntityId& player_id,
    const CriminalFile* criminal_file) const {
    std::vector<NPCMemory> memories;
    for (const NPC& npc : state_.npcs) {
        if (npc.district_id != district_id) continue;
        memories.insert(memories.end(), npc.memories.begin(), npc.memories.end());
    }
    return local_reputation(memories, player_id, criminal_file,
        static_cast<std::uint32_t>(runtime_.day_index()));
}

Consequence SimulationWorld::resolve_offence(
    const DistrictId& district_id, const EntityId& player_id,
    ActionTag action_tag, const EntityId& officer_id, CriminalFile& criminal_file) {
    const auto district = std::find_if(state_.districts.begin(), state_.districts.end(),
        [&district_id](const District& candidate) {
            return candidate.district_id == district_id;
        });
    if (district == state_.districts.end()) {
        throw std::out_of_range("district id not found: " + district_id);
    }
    if (criminal_file.player_id != player_id) {
        throw std::invalid_argument("criminal file belongs to a different player");
    }
    return consequence_for(action_tag, criminal_file, *district, officer_id,
        district->local_corruption, random_.unit_interval());
}

Negotiation SimulationWorld::approach_fixer(
    const DistrictId& district_id, const EntityId& player_id,
    const EntityId& fixer_id, double bribe, const CriminalFile* criminal_file) {
    const auto district = std::find_if(state_.districts.begin(), state_.districts.end(),
        [&district_id](const District& candidate) {
            return candidate.district_id == district_id;
        });
    if (district == state_.districts.end()) {
        throw std::out_of_range("district id not found: " + district_id);
    }
    const auto network = std::find_if(fixer_networks_.begin(), fixer_networks_.end(),
        [&district_id](const FixerNetwork& candidate) {
            return candidate.district_id == district_id;
        });
    if (network == fixer_networks_.end()) {
        throw std::out_of_range("fixer network not found for district: " + district_id);
    }
    const auto fixer = std::find_if(network->members.begin(), network->members.end(),
        [&fixer_id](const FixerProfile& candidate) {
            return candidate.entity_id == fixer_id;
        });
    if (fixer == network->members.end()) {
        throw std::out_of_range("fixer entity id not found: " + fixer_id);
    }

    const double reputation = reputation_in_district(
        district_id, player_id, criminal_file).reputation;
    const auto willingness = willingness_to_deal(reputation, *fixer, *district);
    const double sample = willingness.first ? random_.unit_interval() : 0.0;
    const Negotiation result = negotiate(*fixer, *district, bribe, reputation, sample);
    network->record_outcome(*fixer, result, *district);
    return result;
}

} // namespace simreality

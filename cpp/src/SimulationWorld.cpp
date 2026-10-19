#include "simreality/SimulationWorld.h"

#include "simreality/Decay.h"
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
                if (hour >= 22U || hour < 6U) npc.current_activity = DailyActivity::Sleep;
                else if (hour >= 9U && hour < 17U && !npc.job_id.empty()) npc.current_activity = DailyActivity::Work;
                else if (hour >= 7U && hour < 9U && !npc.job_id.empty()) npc.current_activity = DailyActivity::Commute;
                else if (npc.trauma_level >= TraumaLevel::Paranoid) npc.current_activity = DailyActivity::Home;
                else npc.current_activity = DailyActivity::Socialise;
            }
            const auto district = std::find_if(state_.districts.begin(), state_.districts.end(),
                [&npc](const District& candidate) { return candidate.district_id == npc.district_id; });
            if (district != state_.districts.end() && npc.current_activity == DailyActivity::Commute
                && district->transport_reliability < 0.3) {
                npc.current_activity = DailyActivity::Home;
                npc.personal_stress = std::clamp(npc.personal_stress
                    + (0.3 - district->transport_reliability) * 0.2, 0.0, 1.0);
            }
        }
        if (tick.kind == TickKind::Hourly) {
            for (NPC& npc : state_.npcs) {
                npc.memories = sweep(
                    npc.memories, npc.age_band, tick.at_hour, visibility_weather);
                report.memories_swept += npc.memories.size();
            }
            continue;
        }

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
            double payroll = 0.0;
            double rent_collected = 0.0;
            std::size_t resident_count = 0;
            for (NPC& resident : state_.npcs) {
                if (resident.district_id != district.district_id) continue;
                ++resident_count;
                if (!resident.job_id.empty()) {
                    const double wage = std::max(0.0, resident.hourly_wage) * 8.0;
                    resident.money += wage;
                    payroll += wage;
                }
                const double rent = std::min(std::max(0.0, resident.money), std::max(0.0, resident.daily_rent));
                resident.money -= rent;
                rent_collected += rent;
                const bool shops_during_day = std::any_of(
                    resident.schedule.begin(), resident.schedule.end(),
                    [](const ScheduleEntry& entry) { return entry.activity == DailyActivity::Shop; });
                if ((resident.current_activity == DailyActivity::Shop || shops_during_day)
                    && resident.money > 0.0) {
                    const double purchase = std::min(resident.money, 5.0);
                    resident.money -= purchase;
                    district.shop_stock = std::max(0.0, district.shop_stock - purchase / 100.0);
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
                const double housing_pressure = npc.home_id.empty()
                    ? 0.25 * (1.0 - district.housing_availability) : 0.0;
                const double unemployment_pressure = npc.job_id.empty()
                    ? 0.15 * (1.0 - district.employment_rate) : 0.0;
                const double supply_pressure = 0.2 * district.supply_shortage;
                const double service_relief = npc.current_activity == DailyActivity::Service
                    ? 0.1 * district.service_capacity : 0.0;
                npc.desperation_index = std::clamp(npc.desperation_index
                    + housing_pressure + unemployment_pressure + supply_pressure
                    - service_relief, 0.0, 1.0);
                npc.personal_stress = std::clamp(npc.personal_stress
                    + housing_pressure * 0.2 + unemployment_pressure * 0.2
                    + supply_pressure * 0.1 - service_relief * 0.2, 0.0, 1.0);
                const TraumaAssessment trauma_result =
                    daily_update(npc, npc.desperation_index, 1.0);
                district_result.residents.push_back(
                    {npc.entity_id, behaviour, trauma_result});
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
    Conversation conversation = converse(listener, speaker, listener.district_id);
    // Repeated contact strengthens familiarity; sharing a damaging rumour weakens trust.
    const double change = conversation.transferred.empty() ? 0.02 : -0.01;
    auto& listener_tie = listener.relationships[speaker_id];
    auto& speaker_tie = speaker.relationships[listener_id];
    listener_tie = std::clamp(listener_tie + change, -1.0, 1.0);
    speaker_tie = std::clamp(speaker_tie + change, -1.0, 1.0);
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

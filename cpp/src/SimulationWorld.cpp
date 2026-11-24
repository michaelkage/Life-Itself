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
    WorldState initial_state, double initial_hour, std::uint64_t random_seed,
    double initial_real_time_seconds)
    : state_(std::move(initial_state)),
      runtime_(initial_hour, initial_real_time_seconds),
      random_(random_seed) {}

std::vector<BeliefRevision> SimulationWorld::belief_history_for(
    const EntityId& npc_id, const EntityId& target_id) const {
    const auto npc = std::find_if(
        state_.npcs.begin(), state_.npcs.end(),
        [&npc_id](const NPC& candidate) { return candidate.entity_id == npc_id; });
    if (npc == state_.npcs.end()) return {};

    std::vector<BeliefRevision> history;
    history.reserve(npc->belief_revision_history.size());
    for (const BeliefRevision& revision : npc->belief_revision_history) {
        if (target_id.empty() || revision.target_entity_id == target_id) {
            history.push_back(revision);
        }
    }
    std::stable_sort(history.begin(), history.end(),
        [](const BeliefRevision& left, const BeliefRevision& right) {
            if (left.recorded_hour != right.recorded_hour)
                return left.recorded_hour < right.recorded_hour;
            return left.event_timestamp_hour < right.event_timestamp_hour;
        });
    return history;
}

std::vector<BeliefRevisionExplanation> SimulationWorld::belief_explanations_for(
    const EntityId& npc_id, const EntityId& target_id) const {
    const std::vector<BeliefRevision> history = belief_history_for(npc_id, target_id);
    std::vector<BeliefRevisionExplanation> explanations;
    explanations.reserve(history.size());
    for (const BeliefRevision& revision : history) {
        BeliefRevisionExplanation explanation;
        explanation.revision = revision;
        explanation.confidence_delta =
            revision.revised_confidence - revision.previous_confidence;
        explanation.evidence_claims.reserve(revision.evidence_claim_ids.size());
        for (const std::string& claim_id : revision.evidence_claim_ids) {
            BeliefEvidenceClaimExplanation linked_claim;
            linked_claim.requested_claim_id = claim_id;
            if (const InformationClaim* claim = information_.find(claim_id)) {
                linked_claim.resolved = true;
                linked_claim.claim = *claim;
                linked_claim.lineage = information_.lineage_for_claim(claim_id);
            }
            explanation.evidence_claims.push_back(std::move(linked_claim));
        }
        explanations.push_back(std::move(explanation));
    }
    return explanations;
}

std::vector<NPCBelief> SimulationWorld::beliefs_about_event(
    const EntityId& npc_id, const EntityId& target_id,
    SimulationHour event_timestamp_hour) const {
    if (target_id.empty() || !std::isfinite(event_timestamp_hour)) return {};
    const auto npc = std::find_if(
        state_.npcs.begin(), state_.npcs.end(),
        [&npc_id](const NPC& candidate) { return candidate.entity_id == npc_id; });
    if (npc == state_.npcs.end()) return {};

    std::vector<NPCBelief> accounts;
    for (const NPCBelief& belief : npc->beliefs) {
        if (belief.target_entity_id == target_id
            && belief.timestamp_hour == event_timestamp_hour) {
            accounts.push_back(belief);
        }
    }
    // Canonical ordering is for deterministic display only, not a truth ranking.
    std::stable_sort(accounts.begin(), accounts.end(),
        [](const NPCBelief& left, const NPCBelief& right) {
            if (left.action_tag != right.action_tag)
                return left.action_tag < right.action_tag;
            return left.source_entity_id < right.source_entity_id;
        });
    return accounts;
}


std::vector<BeliefAccountExplanation> SimulationWorld::belief_account_explanations_for(
    const EntityId& npc_id, const EntityId& target_id,
    SimulationHour event_timestamp_hour) const {
    const std::vector<NPCBelief> accounts =
        beliefs_about_event(npc_id, target_id, event_timestamp_hour);
    std::vector<BeliefAccountExplanation> explanations;
    explanations.reserve(accounts.size());
    if (accounts.empty()) return explanations;

    const std::vector<BeliefRevisionExplanation> history =
        belief_explanations_for(npc_id, target_id);
    for (const NPCBelief& account : accounts) {
        BeliefAccountExplanation explanation;
        explanation.current_belief = account;
        for (const BeliefRevisionExplanation& revision : history) {
            if (revision.revision.target_entity_id == account.target_entity_id
                && revision.revision.action_tag == account.action_tag
                && revision.revision.event_timestamp_hour == account.timestamp_hour) {
                explanation.revisions.push_back(revision);
            }
        }
        explanations.push_back(std::move(explanation));
    }
    // Account order follows beliefs_about_event; each account's revisions retain
    // the chronological ordering supplied by belief_explanations_for.
    return explanations;
}

NPCInvestigationView SimulationWorld::investigation_view_for(
    const EntityId& npc_id, const EntityId& target_id) const {
    NPCInvestigationView view;
    view.npc_id = npc_id;

    const auto npc = std::find_if(
        state_.npcs.begin(), state_.npcs.end(),
        [&npc_id](const NPC& candidate) { return candidate.entity_id == npc_id; });
    if (npc == state_.npcs.end()) return view;

    for (InvestigationGroup& group :
        information_.investigation_groups_for(npc_id)) {
        if (target_id.empty() || group.subject_key == target_id) {
            view.received_information.push_back(std::move(group));
        }
    }

    for (const NPCBelief& belief : npc->beliefs) {
        if (target_id.empty() || belief.target_entity_id == target_id) {
            view.current_beliefs.push_back(belief);
        }
    }
    // Stable display order is not a confidence or truth ranking.
    std::stable_sort(view.current_beliefs.begin(), view.current_beliefs.end(),
        [](const NPCBelief& left, const NPCBelief& right) {
            if (left.timestamp_hour != right.timestamp_hour)
                return left.timestamp_hour < right.timestamp_hour;
            if (left.action_tag != right.action_tag)
                return left.action_tag < right.action_tag;
            return left.source_entity_id < right.source_entity_id;
        });

    view.belief_history = belief_explanations_for(npc_id, target_id);

    // Build account-local timelines from the same chronological history. Match
    // the exact target, action interpretation, and event timestamp so revisions
    // for a competing account are never presented as if they explained this one.
    for (const NPCBelief& belief : view.current_beliefs) {
        BeliefAccountExplanation account;
        account.current_belief = belief;
        for (const BeliefRevisionExplanation& revision : view.belief_history) {
            if (revision.revision.target_entity_id == belief.target_entity_id
                && revision.revision.action_tag == belief.action_tag
                && revision.revision.event_timestamp_hour == belief.timestamp_hour) {
                account.revisions.push_back(revision);
            }
        }
        view.belief_accounts.push_back(std::move(account));
    }

    return view;
}

NPCDecisionContextExplanation SimulationWorld::decision_context_for(
    const EntityId& npc_id, const std::vector<MoralChoiceOption>& options,
    const EntityId& target_id) const {
    NPCDecisionContextExplanation context;
    context.npc_id = npc_id;
    context.observed_at_hour = runtime_.total_hours();
    context.investigation = investigation_view_for(npc_id, target_id);

    const auto npc = std::find_if(
        state_.npcs.begin(), state_.npcs.end(),
        [&npc_id](const NPC& candidate) { return candidate.entity_id == npc_id; });
    if (npc == state_.npcs.end()) return context;

    context.relationships = npc->relationships;
    context.option_explanations.reserve(options.size());
    for (const MoralChoiceOption& option : options) {
        context.option_explanations.push_back(explain_moral_choice(*npc, option));
    }
    return context;
}

MoralChoiceResolution SimulationWorld::record_moral_choice(
    const EntityId& npc_id, const std::string& scenario_id,
    const std::vector<MoralChoiceOption>& options,
    const std::vector<MoralChoiceConsequence>& consequences) {
    if (scenario_id.empty()) {
        throw std::invalid_argument("recorded moral choice requires a scenario ID");
    }
    const auto npc = std::find_if(
        state_.npcs.begin(), state_.npcs.end(),
        [&npc_id](const NPC& candidate) { return candidate.entity_id == npc_id; });
    if (npc == state_.npcs.end()) {
        throw std::invalid_argument("recorded moral choice references an unknown NPC");
    }

    // Capture only information already delivered to this NPC before applying effects.
    NPCDecisionRecord record;
    record.recorded_hour = runtime_.total_hours();
    record.scenario_id = scenario_id;
    record.relationship_snapshot = npc->relationships;
    record.loyalty_bias = npc->loyalty_bias;
    record.skepticism = npc->skepticism;
    record.compassion = npc->compassion;
    record.fairness_value = npc->fairness_value;
    record.safety_value = npc->safety_value;
    record.freedom_value = npc->freedom_value;
    record.self_interest_value = npc->self_interest_value;

    for (const InvestigationGroup& group : information_.investigation_groups_for(npc_id)) {
        for (const InvestigationEntry& entry : group.entries) {
            record.evidence_claim_ids.push_back(entry.claim.claim_id);
            if (std::find(record.evidence_root_ids.begin(), record.evidence_root_ids.end(),
                    entry.claim.root_evidence_id) == record.evidence_root_ids.end()) {
                record.evidence_root_ids.push_back(entry.claim.root_evidence_id);
            }
        }
    }
    std::sort(record.evidence_claim_ids.begin(), record.evidence_claim_ids.end());
    std::sort(record.evidence_root_ids.begin(), record.evidence_root_ids.end());

    const MoralChoiceResolution resolution =
        simreality::resolve_moral_choice(*npc, options, consequences);
    record.selected_option_id = resolution.choice.option_id;
    record.selected_score = resolution.choice.score;
    for (const MoralChoiceOption& option : options) {
        record.option_scores.emplace(
            option.option_id, evaluate_moral_choice(*npc, option).score);
    }
    // Scoring depends on stable value traits, which consequences do not mutate.
    npc->decision_history.push_back(std::move(record));
    return resolution;
}

std::vector<NPCDecisionRecord> SimulationWorld::decision_history_for(
    const EntityId& npc_id) const {
    const auto npc = std::find_if(
        state_.npcs.begin(), state_.npcs.end(),
        [&npc_id](const NPC& candidate) { return candidate.entity_id == npc_id; });
    if (npc == state_.npcs.end()) return {};
    return npc->decision_history;
}


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

    // Personality and shared history change how the same event is interpreted.
    // All inputs are already persisted world state; no extra RNG is consumed here.
    const auto relationship = witness->relationships.find(ghost_id);
    const double prior_tie = relationship == witness->relationships.end()
        ? 0.0 : relationship->second;
    double memory_confidence = 0.0;
    for (const NPCMemory& memory : witness->memories) {
        if (memory.target_entity_id == ghost_id) {
            memory_confidence = std::max(memory_confidence, memory.retention);
        }
    }
    const double trauma = static_cast<double>(witness->trauma_level) / 3.0;
    const double fearfulness = std::clamp(
        0.55 * witness->personal_stress + 0.25 * trauma
            + 0.20 * witness->desperation_index, 0.0, 1.0);
    const double closeness = std::clamp((prior_tie + 1.0) * 0.5, 0.0, 1.0);
    const double skepticism = std::clamp(
        1.0 - 0.65 * memory_confidence - 0.35 * closeness, 0.0, 1.0);
    const auto prior_events = static_cast<double>(std::count_if(
        state_.ongoing_events.begin(), state_.ongoing_events.end(),
        [&ghost_id, &npc_id](const OngoingEvent& previous) {
            return previous.actor_id == ghost_id
                && std::find(previous.witness_ids.begin(), previous.witness_ids.end(), npc_id)
                    != previous.witness_ids.end()
                && previous.event_id.find("ghost-influence:") == 0U;
        }));
    const double history = std::min(1.0, prior_events / 5.0);
    const double belief = std::clamp(
        result.score * (1.0 - 0.45 * skepticism) * (0.75 + 0.25 * closeness),
        0.0, 1.0);
    if (action == "sound") {
        const double alarm = fearfulness * (1.0 - 0.55 * closeness);
        witness->personal_stress = std::clamp(witness->personal_stress
            + belief * (0.012 + 0.028 * alarm + 0.012 * history), 0.0, 1.0);
        if (alarm > 0.55 && history >= 0.4) {
            if (std::find(witness->goals.begin(), witness->goals.end(), "avoid_ghost") == witness->goals.end())
                witness->goals.push_back("avoid_ghost");
        } else if (closeness >= 0.65 && belief >= 0.35) {
            if (std::find(witness->goals.begin(), witness->goals.end(), "seek_ghost_contact") == witness->goals.end())
                witness->goals.push_back("seek_ghost_contact");
        }
    } else if (action == "dream") {
        const double comfort = belief * (0.45 + 0.55 * closeness);
        witness->isolation = std::max(0.0, witness->isolation - 0.008 * comfort);
        witness->social_need = std::max(0.0, witness->social_need - 0.006 * comfort);
        witness->personal_stress = std::clamp(witness->personal_stress
            - 0.004 * comfort + 0.004 * fearfulness * skepticism, 0.0, 1.0);
        if (closeness >= 0.6 && history >= 0.4
            && std::find(witness->goals.begin(), witness->goals.end(), "seek_ghost_contact") == witness->goals.end())
            witness->goals.push_back("seek_ghost_contact");
    } else if (action == "sign") {
        double& tie = witness->relationships[ghost_id];
        const double response = belief * (0.012 + 0.018 * closeness)
            - skepticism * fearfulness * (0.008 + 0.012 * history);
        tie = std::clamp(tie + response, -1.0, 1.0);
        if (history >= 0.6 && skepticism >= 0.65) {
            if (std::find(witness->goals.begin(), witness->goals.end(), "investigate_ghost") == witness->goals.end())
                witness->goals.push_back("investigate_ghost");
        } else if (closeness >= 0.65 && belief >= 0.35) {
            if (std::find(witness->goals.begin(), witness->goals.end(), "seek_ghost_contact") == witness->goals.end())
                witness->goals.push_back("seek_ghost_contact");
        }
    }
    return result;
}

WorldAdvanceReport SimulationWorld::advance(
    double elapsed_hours, Weather visibility_weather, double weather_severity) {
    return advance_ticks(runtime_.advance(elapsed_hours), visibility_weather, weather_severity);
}

WorldAdvanceReport SimulationWorld::advance_frame(
    double elapsed_real_seconds, double simulation_hours_per_real_second,
    Weather visibility_weather, double weather_severity) {
    DualClockAdvance frame = runtime_.advance_frame(
        elapsed_real_seconds, simulation_hours_per_real_second);
    return advance_ticks(std::move(frame.simulation_ticks), visibility_weather, weather_severity);
}

WorldAdvanceReport SimulationWorld::advance_ticks(
    std::vector<ScheduledTick> ticks, Weather visibility_weather, double weather_severity) {
    WorldAdvanceReport report;
    report.ticks = std::move(ticks);

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

        // Beliefs are durable interpretations, but even a strongly held account can
        // soften over time. Direct observation and corroboration preserve confidence;
        // unresolved contradictions make an account more fragile. This is deterministic
        // state evolution and deliberately consumes no random samples.
        for (NPC& npc : state_.npcs) {
            for (NPCBelief& belief : npc.beliefs) {
                double daily_decay = belief.directly_observed ? 0.006 : 0.008;
                daily_decay -= static_cast<double>(std::min(belief.corroborations, 4U)) * 0.001;
                daily_decay += static_cast<double>(std::min(belief.contradictions, 4U)) * 0.001;
                daily_decay = std::clamp(daily_decay, 0.002, 0.012);
                belief.confidence = std::clamp(
                    belief.confidence * (1.0 - daily_decay), 0.0, 1.0);
            }
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
            // When homes are scarce, residents with stronger local standing are
            // considered first. This is a soft ordering only: reputation does not
            // change affordability rules or permanently disqualify anyone.
            std::vector<NPC*> housing_candidates;
            for (NPC& resident : state_.npcs) {
                if (resident.district_id == district.district_id && resident.home_id.empty())
                    housing_candidates.push_back(&resident);
            }
            std::stable_sort(housing_candidates.begin(), housing_candidates.end(),
                [this, &district](const NPC* left, const NPC* right) {
                    return community_reputation(left->entity_id, district.district_id)
                        > community_reputation(right->entity_id, district.district_id);
                });
            for (NPC* resident_ptr : housing_candidates) {
                NPC& resident = *resident_ptr;
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
                    double best_hiring_score = -1.0;
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
                        // Hiring weighs reciprocal employee referrals (60%) and
                        // local reputation (40%). Reputation is a soft signal:
                        // conflicting or missing accounts do not automatically ban
                        // a person from work, but can change who gets a scarce slot.
                        const double reputation = community_reputation(
                            resident.entity_id, district.district_id);
                        const double hiring_score = 0.60 * referral
                            + 0.40 * ((std::clamp(reputation, -1.0, 1.0) + 1.0) * 0.5);
                        if (candidate == nullptr || hiring_score > best_hiring_score) {
                            candidate = &resident;
                            best_hiring_score = hiring_score;
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
                            const double recipient_reputation = community_reputation(
                                resident.entity_id, district.district_id);
                            const double assistance_score = 0.65 * trust
                                + 0.35 * recipient_reputation;
                            const double reserve = std::max(20.0, helper.daily_rent * 3.0);
                            // Community standing can open the door to help when a tie
                            // is modest, while a strong reciprocal bond can overcome
                            // a poor reputation. Neither rumours nor reputation alone
                            // can trigger aid without a real personal connection.
                            if (assistance_score < 0.30 || helper.money <= reserve) continue;
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
            case ActionTag::SocialAid: return std::string("Social.Aid");
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
        const ActionTag believed_action = [&rumour]() {
            if (rumour.action_tag == "Social.Aid") return ActionTag::SocialAid;
            if (rumour.action_tag == "Ghost.Sign") return ActionTag::GhostSign;
            if (rumour.action_tag == "Ghost.Sound") return ActionTag::GhostSound;
            if (rumour.action_tag == "Ghost.Dream") return ActionTag::GhostDream;
            if (rumour.action_tag == "Crime.Theft") return ActionTag::CrimeTheft;
            if (rumour.action_tag == "Crime.Assault") return ActionTag::CrimeAssault;
            if (rumour.action_tag == "Crime.ArmedAssault") return ActionTag::CrimeArmedAssault;
            if (rumour.action_tag == "Crime.Vandalism") return ActionTag::CrimeVandalism;
            return ActionTag::InteractionPolite;
        }();
        const std::int64_t claim_tick = static_cast<std::int64_t>(
            std::llround(std::max(0.0, runtime_.total_hours()) * 1000.0));
        const std::string proposition = "action:" + expected_action;
        const std::string root_source = rumour.source_entity_id.empty()
            ? speaker_id : rumour.source_entity_id;
        const std::string root_evidence = "evidence:" + root_source + ":"
            + rumour.target_entity_id + ":" + proposition + ":"
            + std::to_string(std::llround(rumour.timestamp_hour * 1000.0));
        std::string parent_claim_id;
        for (const InformationClaim& received : information_.claims_received_by(speaker_id)) {
            if (received.subject_key == rumour.target_entity_id
                && received.proposition_key == proposition
                && received.root_evidence_id == root_evidence) {
                parent_claim_id = received.claim_id;
            }
        }
        const std::string claim_id = "claim:" + speaker_id + ":" + listener_id + ":"
            + root_evidence + ":" + std::to_string(claim_tick) + ":"
            + std::to_string(information_.size());
        if (!parent_claim_id.empty()) {
            (void)information_.relay(parent_claim_id, claim_id, speaker_id, listener_id,
                claim_tick, std::clamp(rumour.retention, 0.0, 1.0));
        } else {
            InformationClaim claim;
            claim.claim_id = claim_id;
            claim.subject_key = rumour.target_entity_id;
            claim.proposition_key = proposition;
            claim.root_evidence_id = root_evidence;
            claim.source_entity_id = speaker_id;
            claim.recipient_entity_id = listener_id;
            claim.created_tick = claim_tick;
            claim.confidence = std::clamp(rumour.retention, 0.0, 1.0);
            claim.kind = root_source == speaker_id
                ? InformationKind::Observation : InformationKind::Report;
            (void)information_.record(claim);
        }
        double source_reliability = 0.5;
        if (!speaker.beliefs.empty()) {
            double total = 0.0;
            for (const NPCBelief& belief : speaker.beliefs) {
                total += belief.directly_observed ? 1.0 : belief.confidence;
            }
            source_reliability = total / static_cast<double>(speaker.beliefs.size());
        }
        // Personality affects interpretation, not the underlying event record.
        // Neutral traits (0.5) preserve the pre-bias calculation exactly.
        const auto relationship_it = listener.relationships.find(rumour.target_entity_id);
        const double target_tie = relationship_it == listener.relationships.end()
            ? 0.0 : std::clamp(relationship_it->second, -1.0, 1.0);
        const bool prosocial_account = believed_action == ActionTag::SocialAid
            || believed_action == ActionTag::InteractionPolite;
        const bool harmful_account = believed_action == ActionTag::CrimeTheft
            || believed_action == ActionTag::CrimeAssault
            || believed_action == ActionTag::CrimeArmedAssault
            || believed_action == ActionTag::CrimeVandalism;
        const double account_valence = prosocial_account ? 1.0 : (harmful_account ? -1.0 : 0.0);
        const double loyalty_factor = 1.0
            + 0.30 * (std::clamp(listener.loyalty_bias, 0.0, 1.0) - 0.5)
                * target_tie * account_valence;
        const double compassion_factor = 1.0
            + 0.20 * (std::clamp(listener.compassion, 0.0, 1.0) - 0.5)
                * account_valence;
        const double skepticism_factor = 1.0
            - 0.40 * (std::clamp(listener.skepticism, 0.0, 1.0) - 0.5);
        const double account_confidence = std::clamp(
            rumour.retention * (0.55 + 0.25 * std::clamp(prior_trust, -1.0, 1.0)
                + 0.20 * source_reliability) * loyalty_factor * compassion_factor
                * skepticism_factor, 0.0, 1.0);
        auto belief = std::find_if(listener.beliefs.begin(), listener.beliefs.end(),
            [&rumour, &believed_action](const NPCBelief& candidate) {
                return candidate.target_entity_id == rumour.target_entity_id
                    && candidate.timestamp_hour == rumour.timestamp_hour
                    && candidate.action_tag == believed_action;
            });
        // A speaker repeating the same account is not an independent witness.
        // Keep the existing source attribution and do not let repetition inflate
        // confidence, corroboration counts, or the confidence penalty on rivals.
        const bool repeated_source_report = belief != listener.beliefs.end()
            && !belief->directly_observed && belief->source_entity_id == speaker_id;
        bool contradicted = false;
        if (!repeated_source_report) {
            for (NPCBelief& prior : listener.beliefs) {
                if (prior.target_entity_id != rumour.target_entity_id
                    || prior.timestamp_hour != rumour.timestamp_hour
                    || prior.action_tag == believed_action) continue;
                contradicted = true;
                const double previous_confidence = prior.confidence;
                prior.confidence = std::clamp(
                    prior.confidence - 0.20 * account_confidence, 0.0, 1.0);
                ++prior.contradictions;
                BeliefRevision revision;
                revision.target_entity_id = prior.target_entity_id;
                revision.action_tag = prior.action_tag;
                revision.event_timestamp_hour = prior.timestamp_hour;
                revision.previous_confidence = previous_confidence;
                revision.revised_confidence = prior.confidence;
                revision.reason = BeliefRevisionReason::Contradiction;
                revision.source_entity_id = speaker_id;
                revision.recorded_hour = runtime_.total_hours();
                revision.source_reliability = source_reliability;
                revision.loyalty_factor = loyalty_factor;
                revision.compassion_factor = compassion_factor;
                revision.skepticism_factor = skepticism_factor;
                revision.evidence_factor = account_confidence;
                revision.evidence_claim_ids.push_back(claim_id);
                revision.evidence_root_ids.push_back(root_evidence);
                listener.belief_revision_history.push_back(std::move(revision));
            }
        }
        if (belief == listener.beliefs.end()) {
            listener.beliefs.push_back(NPCBelief{rumour.target_entity_id, believed_action,
                rumour.timestamp_hour, account_confidence, speaker_id, false,
                rumour.corroborations, contradicted ? 1U : 0U});
        } else {
            // A first-hand belief keeps its provenance. Only a distinct source
            // can strengthen an existing second-hand account.
            if (!belief->directly_observed && !repeated_source_report) {
                const double previous_confidence = belief->confidence;
                belief->confidence = std::clamp(belief->confidence
                    + (1.0 - belief->confidence) * account_confidence * 0.25, 0.0, 1.0);
                belief->source_entity_id = speaker_id;
                ++belief->corroborations;
                BeliefRevision revision;
                revision.target_entity_id = belief->target_entity_id;
                revision.action_tag = belief->action_tag;
                revision.event_timestamp_hour = belief->timestamp_hour;
                revision.previous_confidence = previous_confidence;
                revision.revised_confidence = belief->confidence;
                revision.reason = BeliefRevisionReason::IndependentEvidence;
                revision.source_entity_id = speaker_id;
                revision.recorded_hour = runtime_.total_hours();
                revision.source_reliability = source_reliability;
                revision.loyalty_factor = loyalty_factor;
                revision.compassion_factor = compassion_factor;
                revision.skepticism_factor = skepticism_factor;
                revision.evidence_factor = account_confidence;
                revision.evidence_claim_ids.push_back(claim_id);
                revision.evidence_root_ids.push_back(root_evidence);
                listener.belief_revision_history.push_back(std::move(revision));
            }
            if (contradicted) ++belief->contradictions;
        }
        if (contradicted) {
            listener.personal_stress = std::clamp(listener.personal_stress + 0.006, 0.0, 1.0);
            if (prior_trust < 0.0) {
                auto& source_tie = listener.relationships[speaker_id];
                source_tie = std::clamp(source_tie - 0.015, -1.0, 1.0);
            }
        }
        if (!rumour.target_entity_id.empty() && rumour.target_entity_id != listener_id) {
            double& target_tie = listener.relationships[rumour.target_entity_id];
            const double evidence = std::clamp(account_confidence, 0.0, 1.0);
            if (believed_action == ActionTag::CrimeTheft || believed_action == ActionTag::CrimeVandalism
                || believed_action == ActionTag::CrimeAssault || believed_action == ActionTag::CrimeArmedAssault) {
                target_tie = std::clamp(target_tie - 0.025 * evidence, -1.0, 1.0);
            } else if (believed_action == ActionTag::InteractionPolite) {
                target_tie = std::clamp(target_tie + 0.008 * evidence, -1.0, 1.0);
            } else if (believed_action == ActionTag::SocialAid) {
                target_tie = std::clamp(target_tie + 0.02 * evidence, -1.0, 1.0);
            }
        }
        const bool ghost_manifestation = expected_action == "Ghost.Sign"
            || expected_action == "Ghost.Sound" || expected_action == "Ghost.Dream";
        const bool already_knew_manifestation = ghost_manifestation
            && std::any_of(memories_before_conversation.begin(), memories_before_conversation.end(),
                [&rumour, &action_name, &expected_action](const NPCMemory& prior) {
                    return prior.target_entity_id == rumour.target_entity_id
                        && action_name(prior.action_tag) == expected_action;
                });
        if (ghost_manifestation && !already_knew_manifestation) {
            // The saved memory is the durable gate against repeating the same story.
            const auto ghost_tie_it = listener.relationships.find(rumour.target_entity_id);
            const double ghost_tie = ghost_tie_it == listener.relationships.end()
                ? 0.0 : ghost_tie_it->second;
            const double closeness = std::clamp((ghost_tie + 1.0) * 0.5, 0.0, 1.0);
            const double fearfulness = std::clamp(
                0.55 * listener.personal_stress
                    + 0.25 * static_cast<double>(listener.trauma_level) / 3.0
                    + 0.20 * listener.desperation_index, 0.0, 1.0);
            const double confidence = std::clamp(rumour.retention, 0.0, 1.0);
            const double skepticism = 1.0 - 0.65 * confidence - 0.35 * closeness;
            const double interpretation = std::clamp(
                confidence * (1.0 - 0.45 * skepticism), 0.0, 1.0);
            if (expected_action == "Ghost.Sound") {
                const double alarm = fearfulness * (1.0 - 0.55 * closeness);
                listener.personal_stress = std::clamp(listener.personal_stress
                    + 0.008 + 0.025 * alarm * interpretation, 0.0, 1.0);
                if (alarm > 0.55
                    && std::find(listener.goals.begin(), listener.goals.end(), "avoid_ghost") == listener.goals.end())
                    listener.goals.push_back("avoid_ghost");
                else if (closeness >= 0.65
                    && std::find(listener.goals.begin(), listener.goals.end(), "seek_ghost_contact") == listener.goals.end())
                    listener.goals.push_back("seek_ghost_contact");
            } else if (expected_action == "Ghost.Dream") {
                const double comfort = interpretation * (0.45 + 0.55 * closeness);
                listener.isolation = std::max(0.0, listener.isolation - 0.008 * comfort);
                listener.social_need = std::max(0.0, listener.social_need - 0.006 * comfort);
                listener.personal_stress = std::clamp(listener.personal_stress
                    - 0.004 * comfort + 0.004 * fearfulness * skepticism, 0.0, 1.0);
            } else {
                double& tie = listener.relationships[rumour.target_entity_id];
                tie = std::clamp(tie + 0.012 * interpretation * (0.5 + 0.5 * closeness)
                    - 0.008 * skepticism * fearfulness, -1.0, 1.0);
                if (skepticism >= 0.65
                    && std::find(listener.goals.begin(), listener.goals.end(), "investigate_ghost") == listener.goals.end())
                    listener.goals.push_back("investigate_ghost");
                else if (closeness >= 0.65
                    && std::find(listener.goals.begin(), listener.goals.end(), "seek_ghost_contact") == listener.goals.end())
                    listener.goals.push_back("seek_ghost_contact");
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
        witness->memories.push_back(memory);
        const auto observed_tick = static_cast<std::int64_t>(
            std::llround(std::max(0.0, runtime_.total_hours()) * 1000.0));
        const std::string observed_proposition = "action:" + std::to_string(static_cast<unsigned int>(action_tag));
        const std::string observed_root = "witnessed:" + witness->entity_id + ":"
            + actor_id + ":" + observed_proposition + ":"
            + std::to_string(std::llround(runtime_.total_hours() * 1000.0));
        const std::string observed_claim_id = "observation:" + observed_root + ":"
            + std::to_string(information_.size());
        InformationClaim observed_claim;
        observed_claim.claim_id = observed_claim_id;
        observed_claim.subject_key = actor_id;
        observed_claim.proposition_key = observed_proposition;
        observed_claim.root_evidence_id = observed_root;
        observed_claim.source_entity_id = witness->entity_id;
        observed_claim.recipient_entity_id = witness->entity_id;
        observed_claim.created_tick = observed_tick;
        observed_claim.confidence = 1.0;
        observed_claim.kind = InformationKind::Observation;
        (void)information_.record(observed_claim);
        // A first-hand observation is strong counter-evidence to a different
        // account about the same target and event hour. Preserve both interpretations,
        // but weaken the conflicting hearsay and record that it was challenged.
        for (NPCBelief& prior : witness->beliefs) {
            if (prior.target_entity_id != actor_id
                || prior.timestamp_hour != runtime_.total_hours()
                || prior.action_tag == action_tag) {
                continue;
            }
            const double previous_confidence = prior.confidence;
            prior.confidence = std::clamp(prior.confidence * 0.75, 0.0, 1.0);
            ++prior.contradictions;
            BeliefRevision revision;
            revision.target_entity_id = prior.target_entity_id;
            revision.action_tag = prior.action_tag;
            revision.event_timestamp_hour = prior.timestamp_hour;
            revision.previous_confidence = previous_confidence;
            revision.revised_confidence = prior.confidence;
            revision.reason = BeliefRevisionReason::Contradiction;
            revision.source_entity_id = witness->entity_id;
            revision.recorded_hour = runtime_.total_hours();
            revision.source_reliability = 1.0;
            revision.evidence_factor = 1.0;
            revision.evidence_claim_ids.push_back(observed_claim_id);
            revision.evidence_root_ids.push_back(observed_root);
            witness->belief_revision_history.push_back(std::move(revision));
        }
        const auto existing_belief = std::find_if(witness->beliefs.begin(), witness->beliefs.end(),
            [&actor_id, action_tag, this](const NPCBelief& belief) {
                return belief.target_entity_id == actor_id && belief.action_tag == action_tag
                    && belief.timestamp_hour == runtime_.total_hours();
            });
        if (existing_belief == witness->beliefs.end()) {
            witness->beliefs.push_back(NPCBelief{actor_id, action_tag, runtime_.total_hours(),
                1.0, witness->entity_id, true, 1U, 0U});
        } else {
            const double previous_confidence = existing_belief->confidence;
            existing_belief->confidence = 1.0;
            existing_belief->directly_observed = true;
            ++existing_belief->corroborations;
            BeliefRevision revision;
            revision.target_entity_id = existing_belief->target_entity_id;
            revision.action_tag = existing_belief->action_tag;
            revision.event_timestamp_hour = existing_belief->timestamp_hour;
            revision.previous_confidence = previous_confidence;
            revision.revised_confidence = 1.0;
            revision.reason = BeliefRevisionReason::IndependentEvidence;
            revision.source_entity_id = witness->entity_id;
            revision.recorded_hour = runtime_.total_hours();
            revision.source_reliability = 1.0;
            revision.evidence_factor = 1.0;
            revision.evidence_claim_ids.push_back(observed_claim_id);
            revision.evidence_root_ids.push_back(observed_root);
            witness->belief_revision_history.push_back(std::move(revision));
        }
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
        case ActionTag::SocialAid: event.severity = 0.0; break;
    }
    for (const NPC* witness : witnesses) event.witness_ids.push_back(witness->entity_id);
    state_.ongoing_events.push_back(std::move(event));
    return witnesses.size();
}

double SimulationWorld::community_reputation(
    const EntityId& target_id, const DistrictId& district_id) const {
    double total = 0.0;
    double weights = 0.0;
    for (const NPC& resident : state_.npcs) {
        if (resident.district_id != district_id || resident.entity_id == target_id) continue;
        for (const NPCBelief& belief : resident.beliefs) {
            if (belief.target_entity_id != target_id) continue;
            double valence = 0.0;
            switch (belief.action_tag) {
                case ActionTag::InteractionPolite:
                    valence = 0.35;
                    break;
                case ActionTag::SocialAid:
                    valence = 0.65;
                    break;
                case ActionTag::CrimeTheft:
                case ActionTag::CrimeAssault:
                case ActionTag::CrimeArmedAssault:
                case ActionTag::CrimeVandalism:
                    valence = -0.7;
                    break;
                case ActionTag::GhostSign:
                case ActionTag::GhostSound:
                case ActionTag::GhostDream:
                    // Supernatural reports affect relationships, not civic reputation.
                    continue;
            }
            const double confidence = std::clamp(belief.confidence, 0.0, 1.0);
            const double observation_weight = belief.directly_observed ? 1.25 : 1.0;
            const double weight = confidence
                * (1.0 + 0.08 * std::min(5.0, static_cast<double>(belief.corroborations)))
                / (1.0 + 0.35 * static_cast<double>(belief.contradictions))
                * observation_weight;
            total += valence * weight;
            weights += weight;
        }
    }
    return weights > 0.0 ? std::clamp(total / weights, -1.0, 1.0) : 0.0;
}

double SimulationWorld::cooperation_score(
    const EntityId& from_id, const EntityId& to_id) const {
    const NPC& from = find_npc(from_id);
    const NPC& to = find_npc(to_id);
    if (from.district_id != to.district_id) return -1.0;
    const auto found = from.relationships.find(to_id);
    const double trust = found == from.relationships.end() ? 0.0
        : std::clamp(found->second, -1.0, 1.0);
    return std::clamp(0.65 * trust
        + 0.35 * community_reputation(to_id, from.district_id), -1.0, 1.0);
}

bool SimulationWorld::offer_support(
    const EntityId& from_id, const EntityId& to_id, double amount) {
    // Invalid support requests are rejected like other unavailable transfers;
    // callers can safely probe an action without unwinding the simulation tick.
    if (!std::isfinite(amount) || amount <= 0.0) return false;
    NPC& donor = find_npc(from_id);
    NPC& recipient = find_npc(to_id);
    if (from_id == to_id || donor.district_id != recipient.district_id
        || donor.money < amount || cooperation_score(from_id, to_id) < -0.15) {
        return false;
    }
    donor.money -= amount;
    recipient.money += amount;
    // Aid is remembered as a durable, attributable social event. The memory
    // uses the existing persisted interaction channel, so it survives snapshots
    // and can be passed on through the ordinary conversation system.
    const SimulationHour event_hour = runtime_.total_hours();
    NPCMemory donor_memory;
    donor_memory.witness_id = from_id;
    donor_memory.target_entity_id = to_id;
    donor_memory.initial_impact = 0.8;
    donor_memory.retention = 1.0;
    donor_memory.timestamp_hour = event_hour;
    donor_memory.action_tag = ActionTag::SocialAid;
    donor.memories.push_back(donor_memory);

    NPCMemory recipient_memory;
    recipient_memory.witness_id = to_id;
    recipient_memory.target_entity_id = from_id;
    recipient_memory.initial_impact = 0.9;
    recipient_memory.retention = 1.0;
    recipient_memory.timestamp_hour = event_hour;
    recipient_memory.action_tag = ActionTag::SocialAid;
    recipient.memories.push_back(recipient_memory);

    // Repeated help compounds into durable reciprocal trust rather than only
    // producing an immediate money transfer.
    donor.relationships[to_id] = std::clamp(
        (donor.relationships.contains(to_id) ? donor.relationships[to_id] : 0.0) + 0.04,
        -1.0, 1.0);
    recipient.relationships[from_id] = std::clamp(
        (recipient.relationships.contains(from_id) ? recipient.relationships[from_id] : 0.0) + 0.03,
        -1.0, 1.0);
    recipient.personal_stress = std::clamp(recipient.personal_stress - 0.02, 0.0, 1.0);
    recipient.desperation_index = std::clamp(recipient.desperation_index - 0.01, 0.0, 1.0);
    return true;
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


void SimulationWorld::set_npc_spatial_state(
    const EntityId& npc_id, SpatialPoint position, SpatialPoint forward,
    SpatialPoint velocity) {
    (void)find_npc(npc_id);
    SpatialPartition::validate_point(position);
    SpatialPartition::validate_point(forward);
    SpatialPartition::validate_point(velocity);
    if (std::hypot(forward.x, forward.y, forward.z) <= 1e-12) {
        throw std::invalid_argument("NPC forward vector must be non-zero");
    }
    spatial_index_.upsert(npc_id, position);
    npc_forward_[npc_id] = forward;
    npc_velocity_[npc_id] = velocity;
}

bool SimulationWorld::remove_npc_spatial_state(const EntityId& npc_id) {
    npc_forward_.erase(npc_id);
    npc_velocity_.erase(npc_id);
    return spatial_index_.erase(npc_id);
}

std::vector<EntityId> SimulationWorld::nearby_npcs(
    SpatialPoint center, double radius) const {
    return spatial_index_.query_radius(center, radius);
}

LaneFollowingResult SimulationWorld::advance_npc_on_lane(
    const EntityId& npc_id, const std::vector<SpatialPoint>& lane_centerline,
    double elapsed_seconds, double lookahead_distance,
    double desired_speed, double maximum_acceleration) {
    (void)find_npc(npc_id);
    if (!spatial_index_.contains(npc_id)) {
        throw std::logic_error("NPC has no registered spatial position: " + npc_id);
    }
    if (!std::isfinite(elapsed_seconds) || elapsed_seconds < 0.0) {
        throw std::invalid_argument("movement delta must be finite and non-negative");
    }
    const SpatialPoint position = spatial_index_.position(npc_id);
    const SpatialPoint velocity = npc_velocity_.at(npc_id);
    const LaneFollowingResult steering = compute_lane_following(
        position, velocity, lane_centerline, lookahead_distance,
        desired_speed, maximum_acceleration);
    SpatialPoint next_velocity{
        velocity.x + steering.steering_force.x * elapsed_seconds,
        velocity.y + steering.steering_force.y * elapsed_seconds,
        velocity.z + steering.steering_force.z * elapsed_seconds};
    const double speed = std::hypot(
        next_velocity.x, next_velocity.y, next_velocity.z);
    if (!std::isfinite(speed)) {
        throw std::overflow_error("NPC movement speed is not representable");
    }
    if (speed > desired_speed && speed > 0.0) {
        const double scale = desired_speed / speed;
        next_velocity.x *= scale;
        next_velocity.y *= scale;
        next_velocity.z *= scale;
    }
    const SpatialPoint next_position{
        position.x + next_velocity.x * elapsed_seconds,
        position.y + next_velocity.y * elapsed_seconds,
        position.z + next_velocity.z * elapsed_seconds};
    SpatialPartition::validate_point(next_position);
    spatial_index_.upsert(npc_id, next_position);
    npc_velocity_[npc_id] = next_velocity;
    if (speed > 1e-12) npc_forward_[npc_id] = next_velocity;
    return steering;
}

LaneFollowingResult SimulationWorld::advance_npc_on_lane_avoiding_collisions(
    const EntityId& npc_id, const std::vector<SpatialPoint>& lane_centerline,
    double elapsed_seconds, double lookahead_distance,
    double desired_speed, double lane_maximum_acceleration,
    double collision_radius, double neighbor_collision_radius,
    double prediction_horizon_seconds, double maximum_avoidance_acceleration,
    double broadphase_radius) {
    (void)find_npc(npc_id);
    if (!spatial_index_.contains(npc_id)) {
        throw std::logic_error("NPC has no registered spatial position: " + npc_id);
    }
    if (!std::isfinite(elapsed_seconds) || elapsed_seconds < 0.0) {
        throw std::invalid_argument("movement delta must be finite and non-negative");
    }
    if (!std::isfinite(broadphase_radius) || broadphase_radius < 0.0) {
        throw std::invalid_argument("collision broadphase radius must be finite and non-negative");
    }
    const SpatialPoint position = spatial_index_.position(npc_id);
    const SpatialPoint velocity = npc_velocity_.at(npc_id);
    const LaneFollowingResult lane = compute_lane_following(
        position, velocity, lane_centerline, lookahead_distance,
        desired_speed, lane_maximum_acceleration);

    std::vector<MovingBody> neighbors;
    const auto candidates = spatial_index_.query_radius(position, broadphase_radius);
    neighbors.reserve(candidates.size());
    for (const EntityId& candidate : candidates) {
        if (candidate == npc_id) continue;
        const auto neighbor_velocity = npc_velocity_.find(candidate);
        if (neighbor_velocity == npc_velocity_.end()) {
            throw std::logic_error("spatial NPC is missing velocity: " + candidate);
        }
        neighbors.push_back({candidate, spatial_index_.position(candidate),
            neighbor_velocity->second, neighbor_collision_radius});
    }
    const CollisionAvoidanceResult avoidance = compute_collision_avoidance(
        npc_id, position, velocity, collision_radius, neighbors,
        prediction_horizon_seconds, maximum_avoidance_acceleration);

    SpatialPoint next_velocity{
        velocity.x + (lane.steering_force.x + avoidance.acceleration.x) * elapsed_seconds,
        velocity.y + (lane.steering_force.y + avoidance.acceleration.y) * elapsed_seconds,
        velocity.z + (lane.steering_force.z + avoidance.acceleration.z) * elapsed_seconds};
    const double speed = std::hypot(next_velocity.x, next_velocity.y, next_velocity.z);
    if (!std::isfinite(speed)) {
        throw std::overflow_error("collision-aware NPC movement speed is not representable");
    }
    if (speed > desired_speed && speed > 0.0) {
        const double scale = desired_speed / speed;
        next_velocity.x *= scale;
        next_velocity.y *= scale;
        next_velocity.z *= scale;
    }
    const SpatialPoint next_position{
        position.x + next_velocity.x * elapsed_seconds,
        position.y + next_velocity.y * elapsed_seconds,
        position.z + next_velocity.z * elapsed_seconds};
    SpatialPartition::validate_point(next_position);
    spatial_index_.upsert(npc_id, next_position);
    npc_velocity_[npc_id] = next_velocity;
    if (speed > 1e-12) npc_forward_[npc_id] = next_velocity;
    return lane;
}

void SimulationWorld::configure_traffic_lane(
    const std::string& lane_id, std::size_t capacity) {
    lane_traffic_.configure_lane(lane_id, capacity);
}

void SimulationWorld::advance_traffic_tick(std::uint64_t tick) {
    lane_traffic_.advance_tick(tick);
}

LaneTrafficResolution SimulationWorld::resolve_lane_traffic(
    const std::vector<LaneTrafficRequest>& requests) {
    return lane_traffic_.resolve(requests);
}

bool SimulationWorld::release_lane_reservation(
    const std::string& lane_id, const EntityId& npc_id) {
    return lane_traffic_.release(lane_id, npc_id);
}

void SimulationWorld::configure_intersection_movement(
    IntersectionMovementDefinition definition) {
    intersection_traffic_.configure_movement(std::move(definition));
}

void SimulationWorld::advance_intersection_tick(std::uint64_t tick) {
    intersection_traffic_.advance_tick(tick);
}

IntersectionTrafficResolution SimulationWorld::resolve_intersection_traffic(
    const std::vector<IntersectionTrafficRequest>& requests) {
    return intersection_traffic_.resolve(requests);
}

bool SimulationWorld::release_intersection_reservation(
    const std::string& intersection_id, const EntityId& npc_id) {
    return intersection_traffic_.release(intersection_id, npc_id);
}

RouteSegmentAdvanceResult SimulationWorld::advance_npc_on_reserved_route_segment(
    const EntityId& npc_id, const RouteSegmentRequest& request) {
    (void)find_npc(npc_id);
    if (request.destination_lane_id.empty()) {
        throw std::invalid_argument("route segment destination lane must not be empty");
    }
    if (request.source_lane_id == request.destination_lane_id
        && !request.source_lane_id.empty()) {
        // Retaining the same lane token is valid; it is not a handoff.
    } else if (!request.source_lane_id.empty()
        && !lane_traffic_.has_reservation(request.source_lane_id, npc_id)) {
        throw std::logic_error("NPC must retain its source-lane reservation during handoff");
    }
    if (!lane_traffic_.has_reservation(request.destination_lane_id, npc_id)) {
        throw std::logic_error("NPC must hold the destination-lane reservation before handoff");
    }

    const bool entering_intersection = !request.entry_intersection_id.empty()
        || !request.entry_movement_id.empty();
    if (entering_intersection
        && (request.entry_intersection_id.empty() || request.entry_movement_id.empty())) {
        throw std::invalid_argument("intersection entry requires both intersection and movement ids");
    }
    if (entering_intersection && !intersection_traffic_.has_reservation(
            request.entry_intersection_id, request.entry_movement_id, npc_id)) {
        throw std::logic_error("NPC must hold the destination intersection movement reservation");
    }

    const bool clearing_intersection = !request.cleared_intersection_id.empty()
        || !request.cleared_movement_id.empty();
    if (clearing_intersection
        && (request.cleared_intersection_id.empty() || request.cleared_movement_id.empty())) {
        throw std::invalid_argument("intersection clearance requires both intersection and movement ids");
    }
    if (clearing_intersection && !intersection_traffic_.has_reservation(
            request.cleared_intersection_id, request.cleared_movement_id, npc_id)) {
        throw std::logic_error("NPC cannot clear an intersection without its active movement reservation");
    }
    if (clearing_intersection && entering_intersection
        && request.cleared_intersection_id == request.entry_intersection_id
        && request.cleared_movement_id == request.entry_movement_id) {
        throw std::invalid_argument("one route segment cannot enter and clear the same movement reservation");
    }

    // All admission checks happen before physical state changes. The source
    // lane and cleared intersection remain reserved until movement commits.
    const LaneFollowingResult movement = advance_npc_on_lane_avoiding_collisions(
        npc_id, request.lane_centerline, request.elapsed_seconds,
        request.lookahead_distance, request.desired_speed,
        request.lane_maximum_acceleration, request.collision_radius,
        request.neighbor_collision_radius, request.prediction_horizon_seconds,
        request.maximum_avoidance_acceleration, request.broadphase_radius);

    RouteSegmentAdvanceResult result;
    result.movement = movement;
    if (!request.source_lane_id.empty()
        && request.source_lane_id != request.destination_lane_id) {
        result.source_lane_released = lane_traffic_.release(request.source_lane_id, npc_id);
    }
    if (clearing_intersection) {
        result.cleared_intersection_released = intersection_traffic_.release(
            request.cleared_intersection_id, npc_id);
    }
    return result;
}

LaneFollowingResult SimulationWorld::advance_npc_on_reserved_intersection_movement(
    const EntityId& npc_id, const std::string& intersection_id,
    const std::string& movement_id,
    const std::vector<SpatialPoint>& lane_centerline,
    double elapsed_seconds, double lookahead_distance,
    double desired_speed, double maximum_acceleration) {
    (void)find_npc(npc_id);
    if (!intersection_traffic_.has_reservation(
            intersection_id, movement_id, npc_id)) {
        throw std::logic_error(
            "NPC must hold the live conflict-zone reservation before entering an intersection");
    }
    return advance_npc_on_lane(npc_id, lane_centerline, elapsed_seconds,
        lookahead_distance, desired_speed, maximum_acceleration);
}

LaneFollowingResult SimulationWorld::advance_npc_on_reserved_lane(
    const EntityId& npc_id, const std::string& lane_id,
    const std::vector<SpatialPoint>& lane_centerline,
    double elapsed_seconds, double lookahead_distance,
    double desired_speed, double maximum_acceleration) {
    (void)find_npc(npc_id);
    if (!lane_traffic_.has_reservation(lane_id, npc_id)) {
        throw std::logic_error("NPC must hold a live lane reservation before movement");
    }
    return advance_npc_on_lane(npc_id, lane_centerline, elapsed_seconds,
        lookahead_distance, desired_speed, maximum_acceleration);
}

std::vector<EntityId> SimulationWorld::visible_npcs(
    SpatialPoint target_position, double maximum_range,
    double field_of_view_radians, const std::set<EntityId>& occluded_npcs) const {
    SpatialPartition::validate_point(target_position);
    if (!std::isfinite(maximum_range) || maximum_range < 0.0) {
        throw std::invalid_argument("visibility range must be finite and non-negative");
    }
    constexpr double full_circle = 6.28318530717958647692;
    if (!std::isfinite(field_of_view_radians) || field_of_view_radians < 0.0
        || field_of_view_radians > full_circle) {
        throw std::invalid_argument("field of view must be finite and in [0, 2*pi]");
    }
    const std::vector<EntityId> candidates = spatial_index_.query_radius(
        target_position, maximum_range);
    std::vector<EntityId> visible;
    visible.reserve(candidates.size());
    for (const EntityId& npc_id : candidates) {
        if (occluded_npcs.contains(npc_id)) continue;
        const auto forward = npc_forward_.find(npc_id);
        if (forward == npc_forward_.end()) {
            throw std::logic_error("spatial NPC is missing its forward vector: " + npc_id);
        }
        const VisionAssessment assessment = assess_vision(
            spatial_index_.position(npc_id), forward->second, target_position,
            maximum_range, field_of_view_radians, false);
        if (assessment.visible) visible.push_back(npc_id);
    }
    return visible;
}


std::vector<EntityId> SimulationWorld::audible_npcs(
    SpatialPoint source_position, double source_power,
    double maximum_range, double ambient_noise,
    const std::map<EntityId, double>& occlusion_attenuation) const {
    SpatialPartition::validate_point(source_position);
    if (!std::isfinite(source_power) || source_power < 0.0
        || !std::isfinite(maximum_range) || maximum_range < 0.0
        || !std::isfinite(ambient_noise) || ambient_noise < 0.0) {
        throw std::invalid_argument(
            "sound power, range, and ambient noise must be finite and non-negative");
    }
    const std::vector<EntityId> candidates = spatial_index_.query_radius(
        source_position, maximum_range);
    std::vector<EntityId> audible;
    audible.reserve(candidates.size());
    for (const EntityId& npc_id : candidates) {
        const auto attenuation = occlusion_attenuation.find(npc_id);
        const double factor = attenuation == occlusion_attenuation.end()
            ? 1.0 : attenuation->second;
        const AcousticAssessment assessment = assess_sound(
            source_position, spatial_index_.position(npc_id), source_power,
            maximum_range, ambient_noise, factor);
        if (assessment.audible) audible.push_back(npc_id);
    }
    return audible;
}



std::size_t SimulationWorld::record_spatially_witnessed_action(
    const EntityId& actor_id, ActionTag action_tag, Description description,
    double maximum_range, double field_of_view_radians,
    const std::set<EntityId>& occluded_npcs, const EntityId& victim_id) {
    (void)find_npc(actor_id);
    if (!spatial_index_.contains(actor_id)) {
        throw std::logic_error("actor has no registered spatial position: " + actor_id);
    }
    std::vector<EntityId> witnesses = visible_npcs(
        spatial_index_.position(actor_id), maximum_range,
        field_of_view_radians, occluded_npcs);
    witnesses.erase(std::remove(witnesses.begin(), witnesses.end(), actor_id),
                    witnesses.end());
    return record_witnessed_action(
        actor_id, action_tag, std::move(description), witnesses, victim_id);
}

} // namespace simreality

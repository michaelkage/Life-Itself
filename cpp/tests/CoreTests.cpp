#include "simreality/CoreTypes.h"
#include "simreality/Campaign.h"
#include "simreality/Decay.h"
#include "simreality/DecisionSystem.h"
#include "simreality/WorldDiagnostics.h"
#include "simreality/Districts.h"
#include "simreality/Ecosystem.h"
#include "simreality/Fixers.h"
#include "simreality/Gossip.h"
#include "simreality/Justice.h"
#include "simreality/LifeSystems.h"
#include "simreality/RandomStream.h"
#include "simreality/Reputation.h"
#include "simreality/SimulationClock.h"
#include "simreality/SimulationRuntime.h"
#include "simreality/SimulationScheduler.h"
#include "simreality/SimulationWorld.h"
#include "simreality/Trauma.h"
#include "simreality/WorldPersistence.h"

#include <cassert>
#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <tuple>

int main() {
    using namespace simreality;

    SimulationClock clock;
    SimulationScheduler scheduler;
    const auto first = clock.advance(23.5);
    const auto first_ticks = scheduler.collect(first);
    assert(first_ticks.size() == 23);
    assert(first_ticks.front().kind == TickKind::Hourly);
    assert(std::abs(first_ticks.front().at_hour - 1.0) < 1e-9);
    assert(std::abs(first_ticks.back().at_hour - 23.0) < 1e-9);

    const auto midnight = clock.advance(1.0);
    const auto midnight_ticks = scheduler.collect(midnight);
    assert(midnight_ticks.size() == 2);
    assert(midnight_ticks[0].kind == TickKind::Hourly);
    assert(midnight_ticks[1].kind == TickKind::Daily);
    assert(std::abs(midnight_ticks[0].at_hour - 24.0) < 1e-9);
    assert(std::abs(midnight_ticks[1].at_hour - 24.0) < 1e-9);

    const auto multi_day = clock.advance(48.0);
    const auto multi_day_ticks = scheduler.collect(multi_day);
    assert(multi_day_ticks.size() == 50); // 48 hourly + daily at 48 and 72.
    assert(multi_day.days_elapsed == 2);
    assert(multi_day.current_day == 3);

    bool rejected_zero = false;
    try {
        (void)clock.advance(0.0);
    } catch (const std::invalid_argument&) {
        rejected_zero = true;
    }
    assert(rejected_zero);

    NPCMemory memory;
    memory.witness_id = "witness-1";
    memory.target_entity_id = "target-1";
    memory.retention = 0.9;
    assert(memory.is_actionable());
    memory.retention = 0.5;
    assert(!memory.is_actionable());
    memory.retention = 0.9;
    memory.target_entity_id.clear();
    assert(!memory.is_actionable());

    RandomStream rng_a(12345U);
    RandomStream rng_b(12345U);
    for (int i = 0; i < 100; ++i) {
        assert(rng_a.next_u64() == rng_b.next_u64());
    }

    RandomStream bounded_rng(42U);
    for (int i = 0; i < 1000; ++i) {
        assert(bounded_rng.bounded(7U) < 7U);
    }
    bool rejected_empty_range = false;
    try {
        (void)bounded_rng.bounded(0U);
    } catch (const std::invalid_argument&) {
        rejected_empty_range = true;
    }
    assert(rejected_empty_range);

    SimulationRuntime runtime;
    const auto runtime_ticks = runtime.advance(24.0);
    assert(runtime_ticks.size() == 25);
    assert(runtime_ticks[23].kind == TickKind::Hourly);
    assert(runtime_ticks[24].kind == TickKind::Daily);
    assert(std::abs(runtime.total_hours() - 24.0) < 1e-9);

    NPCMemory theft;
    theft.witness_id = "witness";
    theft.target_entity_id = "target";
    theft.initial_impact = 1.0;
    theft.retention = 1.0;
    theft.timestamp_hour = 12.0;
    theft.action_tag = ActionTag::CrimeTheft;
    const double theft_after_day = retention_after(theft, AgeBand::Adult, 36.0, Weather::Clear);
    assert(theft_after_day < 0.6);
    assert(theft_after_day >= 0.0);

    NPCMemory armed = theft;
    armed.action_tag = ActionTag::CrimeArmedAssault;
    const double armed_after_year = retention_after(
        armed, AgeBand::YoungAdult, 12.0 + 24.0 * 365.0, Weather::Clear);
    assert(std::abs(armed_after_year - 0.85) < 0.01);

    assert(decay_constant(AgeBand::YoungAdult, ActionTag::CrimeTheft, 12.0, Weather::Clear) >= 0.0);
    assert(visibility_modifier(12.0, Weather::Clear) == visibility_modifier(36.0, Weather::Clear));
    assert(visibility_modifier(0.0, Weather::Clear) == visibility_modifier(24.0, Weather::Clear));
    assert(std::abs(visibility_modifier(36.0, Weather::Clear) - 0.8) < 1e-9);
    assert(std::abs(visibility_modifier(24.0, Weather::Clear) - 1.5) < 1e-9);
    assert(visibility_modifier(12.0, Weather::Clear) < visibility_modifier(0.0, Weather::HeavyRain));

    const auto decayed = sweep({theft}, AgeBand::Adult, 36.0, Weather::Clear);
    assert(decayed.size() == 1);
    assert(decayed[0].retention < theft.retention);


    // Gossip: attribution fades before the physical description does.
    NPCMemory sharp = theft;
    sharp.target_entity_id = "target-42";
    sharp.retention = 0.9;
    sharp.description.height_m = 1.82;
    sharp.description.jacket_colour_weights = {{"black", 0.8}};
    auto named_rumour = retell(sharp);
    assert(named_rumour.has_value());
    assert(named_rumour->target_entity_id == "target-42");

    sharp.retention = 0.5;
    auto vague_rumour = retell(sharp);
    assert(vague_rumour.has_value());
    assert(vague_rumour->target_entity_id.empty());

    sharp.retention = 0.005;
    assert(!retell(sharp).has_value());

    // Exact thresholds are intentional: attribution uses >= 0.6, while
    // the transmission floors reject values <= their respective cutoffs.
    sharp.retention = 0.6;
    auto threshold_rumour = retell(sharp);
    assert(threshold_rumour.has_value());
    assert(threshold_rumour->target_entity_id == "target-42");
    // Once retention falls below the attribution threshold, the rumour becomes
    // appearance-only and uses the lower unattributed transmission floor.
    sharp.retention = 0.05;
    auto low_retention_rumour = retell(sharp);
    assert(low_retention_rumour.has_value());
    assert(low_retention_rumour->target_entity_id.empty());
    sharp.target_entity_id.clear();
    sharp.retention = 0.01;
    assert(!retell(sharp).has_value());
    sharp.retention = 0.0101;
    assert(retell(sharp).has_value());

    Rumour rumour_a{"Crime.Theft", "target-42", sharp.description, 0.9, "D1", 1};
    Rumour rumour_b = rumour_a;
    rumour_b.target_entity_id = "different-target";
    const auto conflict = corroborate(rumour_a, rumour_b);
    assert(conflict.target_entity_id.empty());

    NPC speaker;
    speaker.entity_id = "speaker";
    NPC listener;
    listener.entity_id = "listener";
    NPCMemory matching = theft;
    matching.target_entity_id = "target-42";
    matching.retention = 0.9;
    NPCMemory unrelated = theft;
    unrelated.target_entity_id = "other-target";
    listener.memories = {matching, unrelated};
    speaker.memories = {matching};
    const auto conversation = converse(listener, speaker, "D1");
    assert(conversation.transferred.size() == 1);
    assert(listener.memories.size() == 2);
    assert(listener.memories[0].target_entity_id == "target-42");
    assert(listener.memories[1].target_entity_id == "other-target");

    const auto response = police_response(*vague_rumour, "D1");
    assert(response.find("stop and search") != std::string::npos);

    // Corroboration should improve the physical description without inventing certainty.
    Description first_description;
    first_description.height_m = 1.80;
    first_description.height_uncertainty_m = 0.30;
    first_description.jacket_colour_weights = {{"black", 1.0}, {"brown", 1.0}};
    first_description.masked = false;
    first_description.masked_confidence = 0.9;
    Description second_description;
    second_description.height_m = 1.80;
    second_description.height_uncertainty_m = 0.30;
    second_description.jacket_colour_weights = {{"black", 1.0}};
    second_description.masked = false;
    second_description.masked_confidence = 0.9;
    const auto merged = merge_descriptions(first_description, second_description);
    assert(std::abs(merged.height_m - 1.80) < 1e-9);
    assert(merged.height_uncertainty_m < first_description.height_uncertainty_m);
    assert(jacket_confidence(merged) > jacket_confidence(first_description));

    // Police action is gated by both attribution and description quality.
    Rumour named = rumour_a;
    named.retention = 0.9;
    assert(police_response(named, "D1").find("pursue identification") != std::string::npos);
    Rumour vague;
    vague.target_entity_id.clear();
    vague.retention = 0.4;
    assert(police_response(vague, "D1").find("logged, insufficient detail") != std::string::npos);
    Description single_observation;
    Description five_observations;
    five_observations.observations = 5;
    const Description weighted_merge =
        merge_descriptions(single_observation, five_observations, 0.5);
    assert(weighted_merge.observations == 3); // Python round(2.5) is ties-to-even.

    // Environmental pressure and behaviour selection.
    District pressured;
    pressured.overpopulation = 0.5;
    pressured.supply_shortage = 0.6;
    pressured.weather_severity = 0.5;
    pressured.local_corruption = 0.5;
    pressured.security_presence = 0.4;
    assert(desperation_index(pressured) > 0.53);
    assert(desperation_index(pressured) < 0.54);
    NPC citizen;
    citizen.entity_id = "citizen";
    citizen.moral_shackle = 0.2;
    const auto decision = evaluate(citizen, pressured);
    assert(decision.illegal);
    assert(decision.branch == IllegalBranch::Shoplift);
    assert(decision.reason().find("Shoplift") != std::string::npos);
    pressured.supply_shortage = 0.9;
    assert(evaluate(citizen, pressured).branch == IllegalBranch::CargoHijack);
    pressured.supply_shortage = 0.5;
    pressured.local_corruption = 0.7;
    pressured.overpopulation = 0.6;
    assert(evaluate(citizen, pressured).branch == IllegalBranch::BribeOfficial);
    pressured.overpopulation = 0.8;
    assert(evaluate(citizen, pressured).branch == IllegalBranch::JoinSyndicate);

    std::vector<NPC> residents{citizen};
    const auto daily_behaviour = apply_district_pressure(residents, pressured);
    assert(daily_behaviour.size() == 1);
    assert(residents[0].desperation_index == daily_behaviour[0].desperation_index);

    // District input dynamics and hysteretic city scars.
    District evolving;
    evolving.population = 200;
    evolving.capacity = 100;
    assert(target_overpopulation(evolving) == 1.0);
    evolve_inputs(evolving, 0.6);
    assert(evolving.weather_severity > 0.0);
    assert(evolving.overpopulation > 0.3);
    assert(evolving.supply_shortage > 0.3);

    District scarred;
    scarred.overpopulation = 1.0;
    scarred.supply_shortage = 1.0;
    scarred.weather_severity = 1.0;
    scarred.local_corruption = 1.0;
    scarred.security_presence = 0.0;
    assert(!update_scars(scarred).active);
    assert(!update_scars(scarred).active);
    assert(!update_scars(scarred).active);
    const ScarState scar = update_scars(scarred);
    assert(scar.active);
    assert(scar.boarded_windows());
    assert(scar.police_ignore_minor_offences());
    scarred.overpopulation = 0.0;
    scarred.supply_shortage = 0.0;
    scarred.weather_severity = 0.0;
    scarred.local_corruption = 0.0;
    scarred.security_presence = 1.0;
    for (int day = 0; day < 3; ++day) assert(update_scars(scarred).active);
    assert(!update_scars(scarred).active);

    // Personal trauma and environmental trauma remain separate axes.
    NPC victim;
    assert(absorb(victim, ActionTag::CrimeArmedAssault, true) == 1.0);
    assert(assess(victim, 0.2).level == TraumaLevel::Paranoid);
    assert(assess(NPC{}, 0.9).level == TraumaLevel::Vigilante);
    const auto recovery = daily_update(victim, 0.2, 1.0);
    assert(victim.personal_stress < 1.0);
    assert(recovery.level == TraumaLevel::Paranoid);
    assert(!recovery.permanent());

    // Justice: evidence, corruption, custody outcomes, and plea calculations.
    NPCMemory witness_one = theft;
    witness_one.target_entity_id = "player";
    witness_one.retention = 0.9;
    NPCMemory witness_two = witness_one;
    witness_two.witness_id = "witness-2";
    const CriminalFile corroborated_file =
        file_from_memories("player", {witness_one, witness_two});
    assert(corroborated_file.charges.size() == 1);
    assert(corroborated_file.charges[0].evidence == EvidenceKind::Corroborated);
    assert(corroborated_file.charges[0].provable());
    assert(corroborated_file.charges[0].sentence() == 10.0); // Python round(10.5) == 10.
    const Consequence arrest_result = consequence_for(
        ActionTag::CrimeTheft, corroborated_file, pressured, "officer", 0.0, 0.0);
    assert(std::holds_alternative<Arrest>(arrest_result));
    const CriminalFile empty_file{"player"};
    const Consequence stop_result = consequence_for(
        ActionTag::CrimeTheft, empty_file, pressured, "officer", 0.0, 0.0);
    assert(std::holds_alternative<Stop>(stop_result));
    const Consequence ignored_result = consequence_for(
        ActionTag::CrimeTheft, corroborated_file, pressured, "officer", 1.0, 0.5);
    assert(std::holds_alternative<std::monostate>(ignored_result));

    CriminalFile plea_file = corroborated_file;
    plea_file.charges.push_back(
        {ActionTag::CrimeAssault, EvidenceKind::SingleWitness, 0.7});
    const auto offer = plea_offer(plea_file);
    assert(offer.has_value());
    assert(offer->offered_charge.action_tag == ActionTag::CrimeAssault);
    assert(offer->dropped_charges.size() == 1);
    assert(offer->days_if_tried >= offer->days_if_accepted);
    const Conviction conviction = convict(
        plea_file, ActionTag::CrimeTheft, 10, 30.0);
    assert(conviction.severity() == 0.35);
    assert(plea_file.most_recent_conviction() != nullptr);
    register_bribe_attempt(plea_file);
    assert(plea_file.bribe_attempts == 1);
    assert(plea_file.charges.back().evidence == EvidenceKind::Confessed);

    // Local reputation is deduplicated by offence and conviction records outlive rumours.
    const auto rep = local_reputation({witness_one, witness_two}, "player");
    assert(std::abs(rep.accusation_penalty - 0.2205) < 1e-9);
    assert(std::abs(rep.reputation - 0.7795) < 1e-9);
    const auto convicted_rep = local_reputation(
        {witness_one}, "player", &plea_file, 10);
    assert(convicted_rep.record_penalty > convicted_rep.accusation_penalty);
    assert(std::abs(convicted_rep.reputation - 0.65) < 1e-9);
    assert(!convicted_rep.clean());

    // Fixer incentive and trust propagation.
    FixerProfile fixer{"fixer-1", "D1", 0.5, 0.1};
    FixerProfile peer{"fixer-2", "D1", 0.5, 0.0};
    FixerNetwork network{"D1", {fixer, peer}};
    const Negotiation betrayal = negotiate(fixer, pressured, 0.8, 0.8, 0.0);
    assert(betrayal.accepted && betrayal.bribe_paid && betrayal.betrayed);
    assert(betrayal.squeal_filed);
    network.record_outcome(fixer, betrayal, pressured);
    assert(network.trust() < 0.5);
    assert(known_betrayers({fixer}).size() == 1);
    assert(!willingness_to_deal(0.2, fixer, pressured).first);
    network.daily_update(pressured);
    assert(network.members[0].standing >= kFixerMinStanding);
    assert(network.ceiling(pressured) >= network.trust());

    // End-to-end portable world stepping and social transfer.
    WorldState initial_world;
    District neighbourhood;
    neighbourhood.district_id = "D1";
    neighbourhood.overpopulation = 0.5;
    neighbourhood.supply_shortage = 0.5;
    neighbourhood.weather_severity = 0.5;
    neighbourhood.local_corruption = 0.0;
    neighbourhood.security_presence = 0.4;
    neighbourhood.shop_stock = 0.8;
    neighbourhood.employment_rate = 0.72;
    neighbourhood.housing_availability = 0.15;
    neighbourhood.transport_reliability = 0.65;
    neighbourhood.service_capacity = 0.9;
    neighbourhood.cash_circulation = 2500.0;
    initial_world.districts.push_back(neighbourhood);
    Business shop;
    shop.business_id = "shop-1";
    shop.district_id = "D1";
    shop.stock = 60.0;
    shop.stock_capacity = 100.0;
    shop.cash = 1000.0;
    shop.restock_cost_per_unit = 0.5;
    shop.hourly_wage = 12.5;
    shop.job_slots = 1;
    initial_world.businesses.push_back(shop);
    NPC speaker_npc;
    speaker_npc.entity_id = "speaker";
    speaker_npc.district_id = "D1";
    speaker_npc.home_id = "home-speaker";
    speaker_npc.job_id = "shop-1";
    speaker_npc.hourly_wage = 12.5;
    speaker_npc.daily_rent = 4.0;
    speaker_npc.money = 50.0;
    speaker_npc.relationships["listener"] = 0.75;
    speaker_npc.relationships["player"] = 0.75;
    speaker_npc.goals = {"keep_job", "save_for_home"};
    speaker_npc.schedule = {{DailyActivity::Work, 9, 17}, {DailyActivity::Sleep, 22, 6}};
    NPC listener_npc;
    listener_npc.entity_id = "listener";
    listener_npc.district_id = "D1";
    listener_npc.relationships["speaker"] = 0.75;
    listener_npc.relationships["player"] = 0.75;
    NPC player_npc;
    player_npc.entity_id = "player";
    player_npc.district_id = "D1";
    player_npc.relationships["speaker"] = 0.75;
    player_npc.relationships["listener"] = 0.75;
    initial_world.npcs = {speaker_npc, listener_npc, player_npc};
    HousingUnit shared_home;
    shared_home.unit_id = "home-speaker";
    shared_home.district_id = "D1";
    shared_home.capacity = 3;
    shared_home.daily_rent = 4.0;
    initial_world.housing_units.push_back(shared_home);
    SimulationWorld world(std::move(initial_world), 0.0, 99U);
    Description scene_description;
    scene_description.height_m = 1.82;
    scene_description.jacket_colour_weights = {{"black", 0.8}};
    assert(world.record_witnessed_action(
        "player", ActionTag::CrimeTheft, scene_description,
        {"speaker", "listener", "speaker"}, "listener") == 2);
    assert(world.state().ongoing_events.size() == 1);
    assert(world.state().businesses.size() == 1);
    assert(world.state().businesses[0].stock >= 0.0);
    assert(world.state().businesses[0].cash >= 0.0);
    assert(world.state().ongoing_events[0].actor_id == "player");
    assert(world.state().ongoing_events[0].witness_ids.size() == 2);
    assert(world.state().ongoing_events[0].severity == 0.4);
    assert(world.state().npcs[0].personal_stress > 0.0);
    assert(world.state().npcs[1].personal_stress > world.state().npcs[0].personal_stress);
    const Conversation world_conversation = world.talk("listener", "speaker");
    assert(world_conversation.transferred.size() == 1);
    assert(world.state().npcs[1].memories.size() == 1);
    assert(world.state().npcs[0].beliefs.size() == 1);
    assert(world.state().npcs[0].beliefs[0].directly_observed);
    // The listener was also present at the event, so their belief is first-hand.
    assert(world.state().npcs[1].beliefs.size() == 1);
    assert(world.state().npcs[1].beliefs[0].directly_observed);
    const double first_account_confidence = world.state().npcs[1].beliefs[0].confidence;
    NPC newcomer;
    newcomer.entity_id = "newcomer";
    newcomer.district_id = "D1";
    world.state().npcs.push_back(newcomer);
    const Conversation hearsay_story = world.talk("newcomer", "speaker");
    assert(hearsay_story.transferred.size() == 1);
    const NPC& hearsay_listener = world.state().npcs.back();
    assert(hearsay_listener.beliefs.size() == 1);
    assert(!hearsay_listener.beliefs[0].directly_observed);
    assert(hearsay_listener.beliefs[0].source_entity_id == "speaker");
    NPC contradictor;
    contradictor.entity_id = "contradictor";
    contradictor.district_id = "D1";
    NPCMemory conflicting_account;
    conflicting_account.witness_id = "contradictor";
    conflicting_account.target_entity_id = "player";
    conflicting_account.action_tag = ActionTag::CrimeAssault;
    conflicting_account.timestamp_hour = 0.0;
    conflicting_account.retention = 0.9;
    contradictor.memories.push_back(conflicting_account);
    world.state().npcs.push_back(contradictor);
    const Conversation conflicting_story = world.talk("listener", "contradictor");
    assert(conflicting_story.transferred.size() == 1);
    const NPC& belief_listener = world.state().npcs[1];
    assert(belief_listener.beliefs.size() == 2);
    assert(belief_listener.beliefs[0].confidence < first_account_confidence);
    assert(belief_listener.beliefs[0].contradictions == 1U);
    assert(belief_listener.beliefs[1].action_tag == ActionTag::CrimeAssault);
    assert(belief_listener.beliefs[1].contradictions == 1U);
    assert(belief_listener.personal_stress > 0.0);
    // The community reputation is an aggregate of saved beliefs, not an objective
    // crime flag; contradictory reports temper the weight of each account.
    assert(world.community_reputation("player", "D1") < 0.0);
    // A poor personal relationship plus negative community standing should block support.
    world.state().npcs[1].relationships["player"] = -0.75;
    assert(world.cooperation_score("listener", "player") < 0.0);
    // Ghost stories must not dilute civic reputation for witnessed real-world actions.
    WorldState reputation_probe_state;
    NPC reputation_observer;
    reputation_observer.entity_id = "reputation-observer";
    reputation_observer.district_id = "D1";
    reputation_observer.beliefs.push_back(NPCBelief{
        "target", ActionTag::CrimeTheft, 12.0, 1.0, "reputation-observer", true, 1U, 0U});
    reputation_observer.beliefs.push_back(NPCBelief{
        "target", ActionTag::GhostSound, 12.0, 1.0, "storyteller", false, 1U, 0U});
    reputation_probe_state.npcs.push_back(reputation_observer);
    SimulationWorld reputation_probe(std::move(reputation_probe_state));
    assert(std::abs(reputation_probe.community_reputation("target", "D1") + 0.7) < 1e-9);
    const double listener_money_before_refusal = world.state().npcs[1].money;
    const double player_money_before_refusal = world.state().npcs[2].money;
    // Invalid transfer amounts must be rejected without changing either balance.
    assert(!world.offer_support("listener", "player", 0.0));
    assert(!world.offer_support("listener", "player", -5.0));
    assert(!world.offer_support("listener", "player", std::numeric_limits<double>::quiet_NaN()));
    assert(!world.offer_support("listener", "player", std::numeric_limits<double>::infinity()));
    assert(world.state().npcs[1].money == listener_money_before_refusal);
    assert(world.state().npcs[2].money == player_money_before_refusal);
    assert(!world.offer_support("listener", "player", 5.0));
    assert(world.state().npcs[1].money == listener_money_before_refusal);
    assert(world.state().npcs[2].money == player_money_before_refusal);
    // Save/resume preserves the beliefs and relationship state that decide
    // whether the same support offer is accepted.
    std::stringstream social_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(world, social_snapshot);
    social_snapshot.seekg(0);
    SimulationWorld social_resumed = load_world(social_snapshot);
    world.state().npcs[1].relationships["player"] = 0.9;
    social_resumed.state().npcs[1].relationships["player"] = 0.9;
    // The first load consumed the stream; rewind before creating the isolated test world.
    social_snapshot.clear();
    social_snapshot.seekg(0);
    SimulationWorld support_world = load_world(social_snapshot);
    support_world.state().npcs[1].relationships["player"] = 0.9;
    const double player_money_before_help = support_world.state().npcs[2].money;
    // Give the recipient room for aid to produce a measurable stress/desperation change.
    support_world.state().npcs[2].personal_stress = 0.5;
    social_resumed.state().npcs[2].personal_stress = 0.5;
    support_world.state().npcs[2].desperation_index = 0.5;
    social_resumed.state().npcs[2].desperation_index = 0.5;
    const double stress_before_help = support_world.state().npcs[2].personal_stress;
    const double desperation_before_help = support_world.state().npcs[2].desperation_index;
    const std::size_t donor_memories_before_help = support_world.state().npcs[1].memories.size();
    const std::size_t recipient_memories_before_help = support_world.state().npcs[2].memories.size();
    assert(support_world.offer_support("listener", "player", 5.0));
    assert(social_resumed.offer_support("listener", "player", 5.0));
    assert(support_world.state().npcs[1].money == listener_money_before_refusal - 5.0);
    assert(support_world.state().npcs[2].money == player_money_before_help + 5.0);
    assert(support_world.state().npcs[1].memories.size() == donor_memories_before_help + 1U);
    assert(support_world.state().npcs[2].memories.size() == recipient_memories_before_help + 1U);
    assert(support_world.state().npcs[1].memories.back().target_entity_id == "player");
    assert(support_world.state().npcs[2].memories.back().target_entity_id == "listener");
    assert(support_world.state().npcs[1].memories.back().timestamp_hour == support_world.total_hours());
    assert(support_world.state().npcs[2].memories.back().timestamp_hour == support_world.total_hours());
    assert(support_world.state().npcs[2].personal_stress < stress_before_help);
    assert(support_world.state().npcs[2].desperation_index < desperation_before_help);
    assert(support_world.state().npcs[0].money == social_resumed.state().npcs[0].money);
    assert(support_world.state().npcs[1].money == social_resumed.state().npcs[1].money);
    assert(support_world.state().npcs[1].relationships == social_resumed.state().npcs[1].relationships);
    assert(support_world.state().npcs[1].memories.size() == social_resumed.state().npcs[1].memories.size());
    assert(support_world.state().npcs[2].memories.size() == social_resumed.state().npcs[2].memories.size());
    assert(support_world.state().npcs[2].personal_stress == social_resumed.state().npcs[2].personal_stress);
    assert(support_world.state().npcs[2].desperation_index == social_resumed.state().npcs[2].desperation_index);
    std::stringstream social_bytes_a(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream social_bytes_b(std::ios::in | std::ios::out | std::ios::binary);
    save_world(support_world, social_bytes_a);
    save_world(social_resumed, social_bytes_b);
    assert(social_bytes_a.str() == social_bytes_b.str());
    assert(std::abs(world.state().npcs[0].relationships.at("listener") - 0.755) < 1e-9);
    assert(std::abs(world.state().npcs[1].relationships.at("speaker") - 0.755) < 1e-9);
    // Successful aid is distinguishable from generic politeness when the story
    // reaches a third resident: the recipient gains a positive social belief and
    // the donor's community reputation reflects the account.
    WorldState aid_story_state;
    District aid_story_district;
    aid_story_district.district_id = "aid-story-district";
    aid_story_state.districts.push_back(aid_story_district);
    NPC aid_donor;
    aid_donor.entity_id = "aid-donor";
    aid_donor.district_id = "aid-story-district";
    aid_donor.money = 30.0;
    aid_donor.relationships["aid-recipient"] = 0.9;
    aid_donor.relationships["aid-listener"] = 0.4;
    NPC aid_recipient;
    aid_recipient.entity_id = "aid-recipient";
    aid_recipient.district_id = "aid-story-district";
    aid_recipient.money = 0.0;
    aid_recipient.relationships["aid-donor"] = 0.9;
    aid_recipient.relationships["aid-listener"] = 0.4;
    NPC aid_listener;
    aid_listener.entity_id = "aid-listener";
    aid_listener.district_id = "aid-story-district";
    aid_listener.relationships["aid-recipient"] = 0.2;
    aid_listener.relationships["aid-donor"] = 0.2;
    aid_story_state.npcs = {aid_donor, aid_recipient, aid_listener};
    SimulationWorld aid_story_world(std::move(aid_story_state), 6.0, 41U);
    assert(aid_story_world.offer_support("aid-donor", "aid-recipient", 5.0));
    assert(aid_story_world.state().npcs[0].memories.back().action_tag == ActionTag::SocialAid);
    assert(aid_story_world.state().npcs[1].memories.back().action_tag == ActionTag::SocialAid);
    const double donor_tie_before_story =
        aid_story_world.state().npcs[2].relationships["aid-donor"];
    const Conversation aid_story = aid_story_world.talk("aid-listener", "aid-recipient");
    assert(aid_story.transferred.size() == 1U);
    assert(aid_story.transferred[0].action_tag == "Social.Aid");
    const NPC& aid_listener_after_story = aid_story_world.state().npcs[2];
    assert(aid_listener_after_story.beliefs.size() == 1U);
    assert(aid_listener_after_story.beliefs[0].action_tag == ActionTag::SocialAid);
    assert(aid_listener_after_story.beliefs[0].target_entity_id == "aid-donor");
    assert(aid_listener_after_story.relationships.at("aid-donor") > donor_tie_before_story);
    assert(aid_story_world.community_reputation("aid-donor", "aid-story-district") > 0.0);
    SimulationWorld aid_story_resumed = aid_story_world;
    std::stringstream aid_story_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(aid_story_world, aid_story_snapshot);
    aid_story_snapshot.seekg(0);
    aid_story_resumed = load_world(aid_story_snapshot);
    assert(aid_story_resumed.state().npcs[2].beliefs[0].action_tag == ActionTag::SocialAid);
    assert(aid_story_resumed.community_reputation("aid-donor", "aid-story-district")
        == aid_story_world.community_reputation("aid-donor", "aid-story-district"));
    // A conflicting account about the same target and event hour must coexist
    // with the aid story, reduce its confidence, and lower local standing rather
    // than silently overwriting the first account.
    const double aid_confidence_before_contradiction =
        aid_story_world.state().npcs[2].beliefs[0].confidence;
    NPC aid_contradictor;
    aid_contradictor.entity_id = "aid-contradictor";
    aid_contradictor.district_id = "aid-story-district";
    NPCMemory contradictory_aid_account;
    contradictory_aid_account.witness_id = "aid-contradictor";
    contradictory_aid_account.target_entity_id = "aid-donor";
    contradictory_aid_account.timestamp_hour = aid_story_world.total_hours();
    contradictory_aid_account.action_tag = ActionTag::CrimeTheft;
    contradictory_aid_account.retention = 0.9;
    aid_contradictor.memories.push_back(contradictory_aid_account);
    aid_story_world.state().npcs.push_back(aid_contradictor);
    const Conversation conflicting_aid_story =
        aid_story_world.talk("aid-listener", "aid-contradictor");
    assert(conflicting_aid_story.transferred.size() == 1U);
    const NPC& aid_listener_after_conflict = aid_story_world.state().npcs[2];
    assert(aid_listener_after_conflict.beliefs.size() == 2U);
    assert(aid_listener_after_conflict.beliefs[0].action_tag == ActionTag::SocialAid);
    assert(aid_listener_after_conflict.beliefs[0].confidence < aid_confidence_before_contradiction);
    assert(aid_listener_after_conflict.beliefs[0].contradictions == 1U);
    assert(aid_listener_after_conflict.belief_revision_history.size() == 1U);
    const BeliefRevision& contradiction_revision =
        aid_listener_after_conflict.belief_revision_history.front();
    assert(contradiction_revision.target_entity_id == "aid-donor");
    assert(contradiction_revision.action_tag == ActionTag::SocialAid);
    assert(contradiction_revision.event_timestamp_hour == aid_story_world.total_hours());
    assert(contradiction_revision.previous_confidence == aid_confidence_before_contradiction);
    assert(contradiction_revision.revised_confidence
        == aid_listener_after_conflict.beliefs[0].confidence);
    assert(contradiction_revision.reason == BeliefRevisionReason::Contradiction);
    assert(contradiction_revision.source_entity_id == "aid-contradictor");
    assert(contradiction_revision.recorded_hour == aid_story_world.total_hours());
    assert(contradiction_revision.source_reliability >= 0.0
        && contradiction_revision.source_reliability <= 1.0);
    assert(contradiction_revision.loyalty_factor >= 0.0);
    assert(contradiction_revision.compassion_factor >= 0.0);
    assert(contradiction_revision.skepticism_factor >= 0.0);
    assert(contradiction_revision.evidence_factor >= 0.0);
    assert(contradiction_revision.source_reliability >= 0.0
        && contradiction_revision.source_reliability <= 1.0);
    assert(contradiction_revision.loyalty_factor >= 0.0);
    assert(contradiction_revision.compassion_factor >= 0.0);
    assert(contradiction_revision.skepticism_factor >= 0.0);
    assert(contradiction_revision.evidence_factor >= 0.0);
    assert(aid_listener_after_conflict.beliefs[1].action_tag == ActionTag::CrimeTheft);
    assert(aid_listener_after_conflict.beliefs[1].contradictions == 1U);
    assert(aid_story_world.community_reputation("aid-donor", "aid-story-district") < 0.0);
    std::stringstream conflicting_aid_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(aid_story_world, conflicting_aid_snapshot);
    conflicting_aid_snapshot.seekg(0);
    SimulationWorld conflicting_aid_resumed = load_world(conflicting_aid_snapshot);
    assert(conflicting_aid_resumed.state().npcs[2].beliefs.size() == 2U);
    assert(conflicting_aid_resumed.state().npcs[2].beliefs[0].confidence
        == aid_story_world.state().npcs[2].beliefs[0].confidence);
    assert(conflicting_aid_resumed.state().npcs[2].beliefs[0].contradictions == 1U);
    assert(conflicting_aid_resumed.community_reputation("aid-donor", "aid-story-district")
        == aid_story_world.community_reputation("aid-donor", "aid-story-district"));
    CriminalFile world_file = world.build_criminal_file("player");
    // The conflicting assault account is also a separate observed action in the
    // fixture, so it creates a second charge; the original theft remains corroborated.
    assert(world_file.charges.size() == 2);
    const auto theft_charge = std::find_if(world_file.charges.begin(), world_file.charges.end(),
        [](const Charge& charge) { return charge.action_tag == ActionTag::CrimeTheft; });
    assert(theft_charge != world_file.charges.end());
    assert(theft_charge->evidence == EvidenceKind::Corroborated);
    const auto world_reputation = world.reputation_in_district("D1", "player", &world_file);
    assert(world_reputation.reputation < 1.0);
    const Consequence world_arrest =
        world.resolve_offence("D1", "player", ActionTag::CrimeTheft, "officer", world_file);
    assert(std::holds_alternative<Arrest>(world_arrest));

    FixerNetwork world_network;
    world_network.district_id = "D1";
    world_network.members.push_back(FixerProfile{"world-fixer", "D1", 0.5, 0.1});
    world.fixer_networks().push_back(world_network);
    const Negotiation world_negotiation =
        world.approach_fixer("D1", "player", "world-fixer", 0.8, &world_file);
    assert(world_negotiation.accepted);

    // Poor transport prevents attendance, turning an unreliable commute into lost wages.
    WorldState commute_state;
    District commute_district;
    commute_district.district_id = "commute-district";
    commute_district.transport_reliability = 0.1;
    commute_state.districts.push_back(commute_district);
    NPC commuter;
    commuter.entity_id = "commuter";
    commuter.district_id = "commute-district";
    commuter.job_id = "legacy-employer";
    commuter.hourly_wage = 10.0;
    commuter.money = 0.0;
    commuter.schedule = {{DailyActivity::Commute, 7, 9}, {DailyActivity::Work, 9, 17}, {DailyActivity::Sleep, 22, 6}};
    commute_state.npcs.push_back(commuter);
    SimulationWorld commute_world(std::move(commute_state), 0.0, 11U);
    (void)commute_world.advance(24.0);
    assert(commute_world.state().npcs[0].missed_work_days == 1U);
    assert(commute_world.state().npcs[0].lost_income == 80.0);
    assert(commute_world.state().npcs[0].money == 0.0);

    // Identical snapshots and seeds must produce identical world steps.
    SimulationWorld deterministic_peer = world;
    const WorldAdvanceReport world_report = world.advance(24.0, Weather::Clear, 0.0);
    const WorldAdvanceReport peer_report = deterministic_peer.advance(24.0, Weather::Clear, 0.0);
    assert(world_report.ticks.size() == peer_report.ticks.size());
    assert(world_report.memories_swept == peer_report.memories_swept);
    assert(world_report.daily_results.size() == peer_report.daily_results.size());
    assert(world.state().districts[0].overpopulation ==
        deterministic_peer.state().districts[0].overpopulation);
    assert(world.state().districts[0].supply_shortage ==
        deterministic_peer.state().districts[0].supply_shortage);
    assert(world.state().districts[0].local_corruption ==
        deterministic_peer.state().districts[0].local_corruption);
    assert(world.state().npcs[0].personal_stress ==
        deterministic_peer.state().npcs[0].personal_stress);
    assert(world.state().npcs[0].money > 50.0);
    assert(world.state().districts[0].cash_circulation > 2500.0);
    assert(world.state().npcs[1].desperation_index > 0.0);
    assert(world.state().npcs[1].home_id == "home-speaker");
    assert(world.state().npcs[2].home_id == "home-speaker");
    assert(world.state().districts[0].housing_availability == 0.0);
    assert(world.state().npcs[1].personal_stress ==
        deterministic_peer.state().npcs[1].personal_stress);
    assert(world.fixer_networks()[0].members[0].standing ==
        deterministic_peer.fixer_networks()[0].members[0].standing);
    assert(world.total_hours() == 24.0);
    assert(world.day_index() == 1);
    // Belief/conflicting-account fixtures above add residents and memories;
    // preserve the original minimum without freezing the count to the old fixture.
    assert(world_report.memories_swept >= 48);
    assert(world_report.daily_results.size() == 1);
    assert(world_report.daily_results[0].residents.size() >= 3);

    std::stringstream saved_world(std::ios::in | std::ios::out | std::ios::binary);
    save_world(world, saved_world);
    const std::uint64_t expected_next_random = world.random_stream().next_u64();
    saved_world.seekg(0);
    SimulationWorld restored = load_world(saved_world);
    assert(restored.total_hours() == world.total_hours());
    assert(restored.day_index() == world.day_index());
    assert(restored.state().npcs.size() == world.state().npcs.size());
    assert(restored.state().npcs[0].memories.size() == world.state().npcs[0].memories.size());
    assert(restored.state().npcs[0].home_id == world.state().npcs[0].home_id);
    assert(restored.state().npcs[0].job_id == world.state().npcs[0].job_id);
    assert(restored.state().npcs[0].schedule.size() == world.state().npcs[0].schedule.size());
    assert(restored.state().npcs[0].relationships.at("listener") == world.state().npcs[0].relationships.at("listener"));
    assert(restored.state().npcs[0].goals == world.state().npcs[0].goals);
    assert(restored.state().npcs[0].beliefs.size() == world.state().npcs[0].beliefs.size());
    assert(restored.state().npcs[0].beliefs[0].confidence == world.state().npcs[0].beliefs[0].confidence);
    assert(restored.state().npcs[0].beliefs[0].directly_observed == world.state().npcs[0].beliefs[0].directly_observed);
    assert(restored.state().npcs[0].money == world.state().npcs[0].money);
    assert(restored.state().npcs[0].lost_income == world.state().npcs[0].lost_income);
    assert(restored.state().npcs[0].rent_arrears == world.state().npcs[0].rent_arrears);
    assert(restored.state().housing_units.size() == world.state().housing_units.size());
    assert(restored.state().housing_units[0].unit_id == world.state().housing_units[0].unit_id);
    assert(restored.state().districts[0].shop_stock == world.state().districts[0].shop_stock);
    assert(restored.state().districts[0].cash_circulation == world.state().districts[0].cash_circulation);
    assert(restored.state().ongoing_events.size() == world.state().ongoing_events.size());
    assert(restored.state().ongoing_events[0].event_id == world.state().ongoing_events[0].event_id);
    assert(restored.state().ongoing_events[0].witness_ids == world.state().ongoing_events[0].witness_ids);
    assert(restored.state().ongoing_events[0].investigation_progress ==
        world.state().ongoing_events[0].investigation_progress);
    assert(restored.state().ongoing_events[0].resolved == world.state().ongoing_events[0].resolved);
    assert(restored.fixer_networks().size() == 1);
    assert(restored.fixer_networks()[0].members[0].standing ==
        world.fixer_networks()[0].members[0].standing);
    assert(restored.random_stream().next_u64() == expected_next_random);
    const WorldAdvanceReport original_continuation = world.advance(1.0);
    const WorldAdvanceReport restored_continuation = restored.advance(1.0);
    assert(original_continuation.ticks.size() == restored_continuation.ticks.size());
    assert(original_continuation.ticks[0].kind == restored_continuation.ticks[0].kind);
    assert(world.total_hours() == restored.total_hours());
    assert(world.state().npcs[0].memories[0].retention ==
        restored.state().npcs[0].memories[0].retention);
    assert(world.state().districts[0].overpopulation ==
        restored.state().districts[0].overpopulation);
    assert(world.state().districts[0].local_corruption ==
        restored.state().districts[0].local_corruption);
    assert(world.state().npcs[0].personal_stress ==
        restored.state().npcs[0].personal_stress);
    assert(world.fixer_networks()[0].members[0].standing ==
        restored.fixer_networks()[0].members[0].standing);
    assert(world.random_stream().next_u64() == restored.random_stream().next_u64());

    // A multi-week save/load in the middle must match uninterrupted simulation.
    SimulationWorld multiweek_reference = world;
    SimulationWorld multiweek_resumed = world;
    (void)multiweek_reference.advance(21.0 * 24.0);
    (void)multiweek_resumed.advance(7.0 * 24.0);
    std::stringstream midweek_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(multiweek_resumed, midweek_snapshot);
    midweek_snapshot.seekg(0);
    multiweek_resumed = load_world(midweek_snapshot);
    (void)multiweek_resumed.advance(14.0 * 24.0);
    assert(multiweek_reference.total_hours() == multiweek_resumed.total_hours());
    assert(multiweek_reference.state().businesses.size() == multiweek_resumed.state().businesses.size());
    assert(multiweek_reference.state().businesses[0].stock == multiweek_resumed.state().businesses[0].stock);
    assert(multiweek_reference.state().businesses[0].cash == multiweek_resumed.state().businesses[0].cash);
    assert(multiweek_reference.state().npcs.size() == multiweek_resumed.state().npcs.size());
    for (std::size_t i = 0; i < multiweek_reference.state().npcs.size(); ++i) {
        assert(multiweek_reference.state().npcs[i].money == multiweek_resumed.state().npcs[i].money);
        assert(multiweek_reference.state().npcs[i].job_id == multiweek_resumed.state().npcs[i].job_id);
        assert(multiweek_reference.state().npcs[i].goals == multiweek_resumed.state().npcs[i].goals);
        assert(multiweek_reference.state().npcs[i].memories.size() == multiweek_resumed.state().npcs[i].memories.size());
    }
    assert(multiweek_reference.state().districts[0].supply_shortage ==
        multiweek_resumed.state().districts[0].supply_shortage);
    assert(multiweek_reference.state().ongoing_events[0].investigation_progress ==
        multiweek_resumed.state().ongoing_events[0].investigation_progress);
    assert(multiweek_reference.random_stream().next_u64() == multiweek_resumed.random_stream().next_u64());

    // Repeated shared social hours strengthen reciprocal ties and reduce isolation.
    WorldState social_state;
    District social_district;
    social_district.district_id = "social-district";
    social_state.districts.push_back(social_district);
    NPC social_a;
    social_a.entity_id = "social-a";
    social_a.district_id = "social-district";
    social_a.schedule = {{DailyActivity::Socialise, 9, 17}};
    social_a.isolation = 0.5;
    NPC social_b;
    social_b.entity_id = "social-b";
    social_b.district_id = "social-district";
    social_b.schedule = {{DailyActivity::Socialise, 9, 17}};
    social_b.isolation = 0.5;
    social_state.npcs = {social_a, social_b};
    SimulationWorld social_world(std::move(social_state), 0.0, 12U);
    (void)social_world.advance(12.0);
    assert(social_world.state().npcs[0].relationships.at("social-b") > 0.1);
    assert(social_world.state().npcs[1].relationships.at("social-a") > 0.1);
    assert(social_world.state().npcs[0].isolation < 0.5);
    assert(social_world.state().npcs[1].social_need < 0.25);

    // A scheduled shopping hour transfers money into a real shop and consumes stock.
    WorldState shopping_state;
    District shopping_district;
    shopping_district.district_id = "shopping-district";
    shopping_state.districts.push_back(shopping_district);
    NPC shopper;
    shopper.entity_id = "shopper";
    shopper.district_id = "shopping-district";
    shopper.money = 100.0;
    shopper.schedule = {{DailyActivity::Shop, 9, 10}};
    shopping_state.npcs.push_back(shopper);
    Business test_shop;
    test_shop.business_id = "test-shop";
    test_shop.district_id = "shopping-district";
    test_shop.stock = 20.0;
    test_shop.stock_capacity = 20.0;
    test_shop.cash = 50.0;
    shopping_state.businesses.push_back(test_shop);
    SimulationWorld shopping_world(std::move(shopping_state), 0.0, 13U);
    (void)shopping_world.advance(12.0);
    assert(shopping_world.state().npcs[0].money == 95.0);
    assert(shopping_world.state().businesses[0].stock == 15.0);
    assert(shopping_world.state().businesses[0].cash == 55.0);

    // Service attendance provides an actual wellbeing benefit.
    WorldState service_state;
    District service_district;
    service_district.district_id = "service-district";
    service_district.service_capacity = 1.0;
    service_state.districts.push_back(service_district);
    NPC service_user;
    service_user.entity_id = "service-user";
    service_user.district_id = "service-district";
    service_user.personal_stress = 0.5;
    service_user.schedule = {{DailyActivity::Service, 9, 11}};
    service_state.npcs.push_back(service_user);
    SimulationWorld service_world(std::move(service_state), 0.0, 14U);
    (void)service_world.advance(12.0);
    assert(service_world.state().npcs[0].personal_stress < 0.5);

    // Trusted ties make affordable shared housing possible and split rent.
    WorldState shared_home_state;
    District shared_home_district;
    shared_home_district.district_id = "shared-home-district";
    shared_home_state.districts.push_back(shared_home_district);
    HousingUnit shared_unit;
    shared_unit.unit_id = "trusted-home";
    shared_unit.district_id = "shared-home-district";
    shared_unit.capacity = 2;
    shared_unit.daily_rent = 30.0;
    shared_home_state.housing_units.push_back(shared_unit);
    NPC existing_housemate;
    existing_housemate.entity_id = "existing-housemate";
    existing_housemate.district_id = "shared-home-district";
    existing_housemate.home_id = "trusted-home";
    existing_housemate.money = 50.0;
    existing_housemate.relationships["new-housemate"] = 0.8;
    NPC new_housemate;
    new_housemate.entity_id = "new-housemate";
    new_housemate.district_id = "shared-home-district";
    new_housemate.money = 50.0; // Can afford half the rent, not the whole unit.
    new_housemate.relationships["existing-housemate"] = 0.8;
    shared_home_state.npcs = {existing_housemate, new_housemate};
    SimulationWorld shared_home_world(std::move(shared_home_state), 0.0, 21U);
    (void)shared_home_world.advance(24.0);
    assert(shared_home_world.state().npcs[1].home_id == "trusted-home");
    assert(shared_home_world.state().npcs[0].daily_rent == 15.0);
    assert(shared_home_world.state().npcs[1].daily_rent == 15.0);

    // Trusted friends provide a small bridge loan when income loss threatens rent.
    WorldState aid_state;
    District aid_district;
    aid_district.district_id = "aid-district";
    aid_state.districts.push_back(aid_district);
    NPC struggling;
    struggling.entity_id = "struggling";
    struggling.district_id = "aid-district";
    struggling.money = 0.0;
    struggling.daily_rent = 5.0;
    struggling.lost_income = 20.0;
    struggling.relationships["supporter"] = 0.8;
    NPC supporter;
    supporter.entity_id = "supporter";
    supporter.district_id = "aid-district";
    supporter.money = 100.0;
    supporter.relationships["struggling"] = 0.8;
    aid_state.npcs = {struggling, supporter};
    SimulationWorld aid_world(std::move(aid_state), 0.0, 22U);
    (void)aid_world.advance(24.0);
    assert(aid_world.state().npcs[1].money < 100.0);
    assert(aid_world.state().npcs[0].rent_arrears == 0.0);

    // Employers prefer a candidate recommended by a trusted existing employee.
    WorldState referral_state;
    District referral_district;
    referral_district.district_id = "referral-district";
    referral_state.districts.push_back(referral_district);
    NPC employee;
    employee.entity_id = "employee";
    employee.district_id = "referral-district";
    employee.job_id = "referral-shop";
    employee.hourly_wage = 1.0;
    employee.relationships["recommended"] = 0.9;
    NPC recommended;
    recommended.entity_id = "recommended";
    recommended.district_id = "referral-district";
    recommended.relationships["employee"] = 0.9;
    NPC stranger;
    stranger.entity_id = "stranger";
    stranger.district_id = "referral-district";
    referral_state.npcs = {employee, stranger, recommended};
    Business referral_shop;
    referral_shop.business_id = "referral-shop";
    referral_shop.district_id = "referral-district";
    referral_shop.cash = 1000.0;
    referral_shop.job_slots = 2;
    referral_state.businesses.push_back(referral_shop);
    SimulationWorld referral_world(std::move(referral_state), 0.0, 23U);
    (void)referral_world.advance(24.0);
    assert(referral_world.state().npcs[2].job_id == "referral-shop");
    assert(referral_world.state().npcs[1].job_id.empty());

    // Community standing can widen access to automatic aid without replacing personal trust.
    const auto verify_reputation_aid = [](ActionTag standing_action, double reciprocal_trust) {
        WorldState aid_state;
        District aid_district;
        aid_district.district_id = "reputation-aid-district";
        aid_state.districts.push_back(aid_district);
        NPC aid_witness;
        aid_witness.entity_id = "aid-witness";
        aid_witness.district_id = "reputation-aid-district";
        aid_witness.beliefs.push_back(NPCBelief{
            "aid-recipient", standing_action, 0.0, 0.9,
            "aid-witness", true, 1U, 0U});
        NPC aid_recipient;
        aid_recipient.entity_id = "aid-recipient";
        aid_recipient.district_id = "reputation-aid-district";
        aid_recipient.money = 0.0;
        aid_recipient.daily_rent = 10.0;
        aid_recipient.lost_income = 1.0;
        aid_recipient.personal_stress = 0.5;
        aid_recipient.desperation_index = 0.5;
        aid_recipient.relationships["aid-helper"] = reciprocal_trust;
        NPC aid_helper;
        aid_helper.entity_id = "aid-helper";
        aid_helper.district_id = "reputation-aid-district";
        aid_helper.money = 100.0;
        aid_helper.relationships["aid-recipient"] = reciprocal_trust;
        aid_state.npcs = {aid_witness, aid_recipient, aid_helper};
        SimulationWorld aid_world(aid_state, 0.0, 77U);
        (void)aid_world.advance(24.0);
        return aid_world;
    };
    SimulationWorld reputation_enabled_aid = verify_reputation_aid(
        ActionTag::InteractionPolite, 0.30);
    // The gift is applied to rent during the same daily tick, so the helper's
    // balance and the recipient's reduced strain are the durable evidence of aid.
    assert(reputation_enabled_aid.state().npcs[2].money < 100.0);
    assert(reputation_enabled_aid.state().npcs[1].personal_stress < 0.5);
    // A strong reciprocal bond still helps despite a negative local reputation.
    SimulationWorld bond_overcomes_reputation = verify_reputation_aid(
        ActionTag::CrimeTheft, 0.90);
    assert(bond_overcomes_reputation.state().npcs[2].money < 100.0);
    assert(bond_overcomes_reputation.state().npcs[1].personal_stress < 0.5);

    // Reputation softly prioritizes scarce housing without replacing affordability checks.
    WorldState reputation_housing_state;
    District reputation_housing_district;
    reputation_housing_district.district_id = "reputation-housing-district";
    reputation_housing_state.districts.push_back(reputation_housing_district);
    HousingUnit scarce_home;
    scarce_home.unit_id = "scarce-home";
    scarce_home.district_id = "reputation-housing-district";
    scarce_home.capacity = 1;
    scarce_home.daily_rent = 10.0;
    reputation_housing_state.housing_units.push_back(scarce_home);
    NPC housing_witness;
    housing_witness.entity_id = "housing-witness";
    housing_witness.district_id = "reputation-housing-district";
    housing_witness.beliefs.push_back(NPCBelief{
        "trusted-housing-applicant", ActionTag::InteractionPolite, 0.0, 0.9,
        "housing-witness", true, 1U, 0U});
    housing_witness.beliefs.push_back(NPCBelief{
        "poor-standing-applicant", ActionTag::CrimeTheft, 0.0, 0.9,
        "housing-witness", true, 1U, 0U});
    NPC poor_standing_applicant;
    poor_standing_applicant.entity_id = "poor-standing-applicant";
    poor_standing_applicant.district_id = "reputation-housing-district";
    poor_standing_applicant.money = 100.0;
    NPC trusted_housing_applicant;
    trusted_housing_applicant.entity_id = "trusted-housing-applicant";
    trusted_housing_applicant.district_id = "reputation-housing-district";
    trusted_housing_applicant.money = 100.0;
    reputation_housing_state.npcs = {
        housing_witness, poor_standing_applicant, trusted_housing_applicant};
    SimulationWorld housing_reference(reputation_housing_state, 0.0, 25U);
    SimulationWorld housing_resumed(reputation_housing_state, 0.0, 25U);
    (void)housing_reference.advance(24.0);
    (void)housing_resumed.advance(12.0);
    std::stringstream housing_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(housing_resumed, housing_snapshot);
    housing_snapshot.seekg(0);
    housing_resumed = load_world(housing_snapshot);
    (void)housing_resumed.advance(12.0);
    assert(housing_reference.state().npcs[2].home_id == "scarce-home");
    assert(housing_reference.state().npcs[1].home_id.empty());
    assert(housing_resumed.state().npcs[2].home_id == "scarce-home");
    assert(housing_reference.state().npcs[2].daily_rent
        == housing_resumed.state().npcs[2].daily_rent);
    std::stringstream housing_reference_bytes(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream housing_resumed_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_world(housing_reference, housing_reference_bytes);
    save_world(housing_resumed, housing_resumed_bytes);
    assert(housing_reference_bytes.str() == housing_resumed_bytes.str());

    // Community reputation can decide a scarce job slot when applicants have equal referrals.
    // A directly witnessed polite interaction helps standing; a witnessed theft harms it.
    WorldState reputation_hiring_state;
    District reputation_hiring_district;
    reputation_hiring_district.district_id = "reputation-hiring-district";
    reputation_hiring_state.districts.push_back(reputation_hiring_district);
    NPC hiring_witness;
    hiring_witness.entity_id = "hiring-witness";
    hiring_witness.district_id = "reputation-hiring-district";
    hiring_witness.beliefs.push_back(NPCBelief{
        "trusted-worker", ActionTag::InteractionPolite, 0.0, 0.9,
        "hiring-witness", true, 1U, 0U});
    hiring_witness.beliefs.push_back(NPCBelief{
        "poor-standing-worker", ActionTag::CrimeTheft, 0.0, 0.9,
        "hiring-witness", true, 1U, 0U});
    NPC poor_standing_worker;
    poor_standing_worker.entity_id = "poor-standing-worker";
    poor_standing_worker.district_id = "reputation-hiring-district";
    NPC trusted_worker;
    trusted_worker.entity_id = "trusted-worker";
    trusted_worker.district_id = "reputation-hiring-district";
    reputation_hiring_state.npcs = {hiring_witness, poor_standing_worker, trusted_worker};
    Business reputation_hiring_shop;
    reputation_hiring_shop.business_id = "reputation-hiring-shop";
    reputation_hiring_shop.district_id = "reputation-hiring-district";
    reputation_hiring_shop.cash = 1000.0;
    reputation_hiring_shop.job_slots = 1;
    reputation_hiring_state.businesses.push_back(reputation_hiring_shop);
    SimulationWorld reputation_hiring_reference(reputation_hiring_state, 0.0, 24U);
    SimulationWorld reputation_hiring_resumed(reputation_hiring_state, 0.0, 24U);
    (void)reputation_hiring_reference.advance(24.0);
    (void)reputation_hiring_resumed.advance(12.0);
    std::stringstream reputation_hiring_snapshot(
        std::ios::in | std::ios::out | std::ios::binary);
    save_world(reputation_hiring_resumed, reputation_hiring_snapshot);
    reputation_hiring_snapshot.seekg(0);
    reputation_hiring_resumed = load_world(reputation_hiring_snapshot);
    (void)reputation_hiring_resumed.advance(12.0);
    assert(reputation_hiring_reference.community_reputation(
        "trusted-worker", "reputation-hiring-district") > 0.0);
    assert(reputation_hiring_reference.community_reputation(
        "poor-standing-worker", "reputation-hiring-district") < 0.0);
    assert(reputation_hiring_reference.state().npcs[2].job_id == "reputation-hiring-shop");
    assert(reputation_hiring_reference.state().npcs[1].job_id.empty());
    assert(reputation_hiring_resumed.state().npcs[2].job_id == "reputation-hiring-shop");
    assert(reputation_hiring_reference.state().npcs[2].money
        == reputation_hiring_resumed.state().npcs[2].money);
    std::stringstream hiring_reference_bytes(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream hiring_resumed_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_world(reputation_hiring_reference, hiring_reference_bytes);
    save_world(reputation_hiring_resumed, hiring_resumed_bytes);
    assert(hiring_reference_bytes.str() == hiring_resumed_bytes.str());

    // Trusted sources reinforce retained information; hostile sources spread weaker, less certain rumours.
    WorldState trusted_gossip_state;
    District trusted_gossip_district;
    trusted_gossip_district.district_id = "gossip-district";
    trusted_gossip_state.districts.push_back(trusted_gossip_district);
    NPC trusted_listener;
    trusted_listener.entity_id = "trusted-listener";
    trusted_listener.district_id = "gossip-district";
    trusted_listener.relationships["trusted-speaker"] = 0.8;
    NPC trusted_speaker;
    trusted_speaker.entity_id = "trusted-speaker";
    trusted_speaker.district_id = "gossip-district";
    trusted_speaker.relationships["trusted-listener"] = 0.8;
    NPCMemory trusted_memory = theft;
    trusted_memory.target_entity_id = "rumour-target";
    trusted_memory.retention = 0.8;
    trusted_memory.description.height_uncertainty_m = 0.2;
    trusted_speaker.memories.push_back(trusted_memory);
    trusted_gossip_state.npcs = {trusted_listener, trusted_speaker};
    SimulationWorld trusted_gossip_world(std::move(trusted_gossip_state), 0.0, 24U);
    (void)trusted_gossip_world.talk("trusted-listener", "trusted-speaker");
    assert(trusted_gossip_world.state().npcs[0].memories[0].retention > 0.8);

    WorldState untrusted_gossip_state;
    District untrusted_gossip_district;
    untrusted_gossip_district.district_id = "gossip-district";
    untrusted_gossip_state.districts.push_back(untrusted_gossip_district);
    NPC untrusted_listener;
    untrusted_listener.entity_id = "untrusted-listener";
    untrusted_listener.district_id = "gossip-district";
    untrusted_listener.relationships["untrusted-speaker"] = -0.6;
    NPC untrusted_speaker;
    untrusted_speaker.entity_id = "untrusted-speaker";
    untrusted_speaker.district_id = "gossip-district";
    untrusted_speaker.relationships["untrusted-listener"] = -0.6;
    NPCMemory untrusted_memory = theft;
    untrusted_memory.target_entity_id = "uncertain-target";
    untrusted_memory.retention = 0.8;
    untrusted_memory.description.height_uncertainty_m = 0.2;
    untrusted_speaker.memories.push_back(untrusted_memory);
    untrusted_gossip_state.npcs = {untrusted_listener, untrusted_speaker};
    SimulationWorld untrusted_gossip_world(std::move(untrusted_gossip_state), 0.0, 25U);
    (void)untrusted_gossip_world.talk("untrusted-listener", "untrusted-speaker");
    assert(untrusted_gossip_world.state().npcs[0].memories[0].retention < 0.8);
    assert(untrusted_gossip_world.state().npcs[0].memories[0].description.height_uncertainty_m > 0.2);

    // Utility-based fallback decisions respond to needs, time and available options.
    NPC decision_npc;
    decision_npc.entity_id = "decision-npc";
    decision_npc.social_need = 0.9;
    decision_npc.isolation = 0.8;
    ActivityContext social_context;
    social_context.hour = 14;
    const ActivityDecision social_decision = choose_activity(decision_npc, nullptr, social_context);
    assert(social_decision.activity == DailyActivity::Socialise);
    assert(!social_decision.reason.empty());
    decision_npc.job_id = "legacy-job";
    ActivityContext work_context;
    work_context.hour = 12;
    assert(choose_activity(decision_npc, nullptr, work_context).activity == DailyActivity::Work);
    work_context.hour = 23;
    assert(choose_activity(decision_npc, nullptr, work_context).activity == DailyActivity::Sleep);

    // Read-only diagnostics expose whole-world health and reject broken references.
    WorldState diagnostic_state;
    District diagnostic_district;
    diagnostic_district.district_id = "diagnostic-district";
    diagnostic_state.districts.push_back(diagnostic_district);
    HousingUnit diagnostic_home;
    diagnostic_home.unit_id = "diagnostic-home";
    diagnostic_home.district_id = "diagnostic-district";
    diagnostic_home.capacity = 1;
    diagnostic_state.housing_units.push_back(diagnostic_home);
    Business diagnostic_shop;
    diagnostic_shop.business_id = "diagnostic-shop";
    diagnostic_shop.district_id = "diagnostic-district";
    diagnostic_shop.stock = 25.0;
    diagnostic_shop.stock_capacity = 30.0;
    diagnostic_shop.cash = 40.0;
    diagnostic_state.businesses.push_back(diagnostic_shop);
    NPC diagnostic_resident;
    diagnostic_resident.entity_id = "diagnostic-resident";
    diagnostic_resident.district_id = "diagnostic-district";
    diagnostic_resident.home_id = "diagnostic-home";
    diagnostic_resident.job_id = "diagnostic-shop";
    diagnostic_resident.money = 75.0;
    diagnostic_resident.personal_stress = 0.4;
    diagnostic_state.npcs.push_back(diagnostic_resident);
    OngoingEvent diagnostic_event;
    diagnostic_event.event_id = "diagnostic-event";
    diagnostic_event.district_id = "diagnostic-district";
    diagnostic_state.ongoing_events.push_back(diagnostic_event);
    const WorldMetrics metrics = collect_world_metrics(diagnostic_state);
    assert(metrics.residents == 1);
    assert(metrics.housed_residents == 1);
    assert(metrics.employed_residents == 1);
    assert(metrics.open_businesses == 1);
    assert(metrics.unresolved_events == 1);
    assert(metrics.resident_cash == 75.0);
    assert(metrics.business_cash == 40.0);
    assert(metrics.available_business_stock == 25.0);
    assert(std::abs(metrics.average_stress - 0.4) < 1e-9);
    assert(validate_world_state(diagnostic_state).valid());
    diagnostic_state.npcs[0].home_id = "missing-home";
    assert(!validate_world_state(diagnostic_state).valid());

    bool rejected_bad_snapshot = false;
    try {
        std::stringstream invalid_snapshot("not-a-snapshot");
        (void)load_world(invalid_snapshot);
    } catch (const std::runtime_error&) {
        rejected_bad_snapshot = true;
    }
    assert(rejected_bad_snapshot);

    // Persistent health, medical uncertainty, death and personality-aware ghost windows.
    LifeCoordinator lives;
    lives.register_character("life-dead");
    MedicalCondition injury;
    injury.condition_id = "injury";
    injury.severity = 0.8;
    injury.recovery_per_day = 0.1;
    injury.work_capacity_at_full_severity = 0.2;
    lives.add_condition("life-dead", injury);
    MedicalTreatment care;
    care.treatment_id = "rest";
    care.condition_id = "injury";
    care.effectiveness = 0.5;
    care.daily_cost = 2.0;
    lives.add_treatment("life-dead", care);
    const RecoveryRange range = lives.estimate_recovery("life-dead", "injury");
    assert(range.lower <= range.expected);
    assert(range.upper >= range.expected);
    assert(lives.kill("life-dead", 2U, "illness"));
    assert(lives.enter_ghost("life-dead"));
    lives.set_ghost_windows({GhostTimeWindow{2.0, 4.0, 1.0}});
    WorldState ghost_state;
    NPC receptive_npc;
    receptive_npc.entity_id = "receptive";
    receptive_npc.relationships["life-dead"] = 1.0;
    NPCMemory remembered;
    remembered.target_entity_id = "life-dead";
    remembered.retention = 0.9;
    remembered.action_tag = ActionTag::CrimeAssault;
    receptive_npc.memories.push_back(remembered);
    ghost_state.npcs.push_back(receptive_npc);
    const auto blocked_ghost = lives.attempt_ghost_influence(
        "life-dead", "receptive", "sound", 1.0, ghost_state, 0U);
    assert(!blocked_ghost.accepted);
    const auto allowed_ghost = lives.attempt_ghost_influence(
        "life-dead", "receptive", "sound", 3.0, ghost_state, 0U);
    assert(allowed_ghost.accepted);
    assert(allowed_ghost.score > 0.7);
    assert(ghost_state.npcs.back().memories.size() == 2U);
    assert(ghost_state.npcs.back().memories.front().retention == 0.9);
    assert(ghost_state.npcs.back().memories.back().action_tag == ActionTag::GhostSound);
    assert(ghost_state.npcs.back().memories.back().retention == 0.03);
    const std::size_t memories_after_success = ghost_state.npcs.back().memories.size();
    const auto forbidden_ghost = lives.attempt_ghost_influence(
        "life-dead", "receptive", "comfort", 3.0, ghost_state, 0U);
    assert(!forbidden_ghost.accepted);
    assert(forbidden_ghost.reason == "outside permitted time/action window");
    assert(ghost_state.npcs.back().memories.size() == memories_after_success);

    // The same sound is interpreted differently by fearful, skeptical, and close NPCs.
    WorldState interpretation_state;
    NPC fearful;
    fearful.entity_id = "fearful";
    fearful.district_id = "shared";
    fearful.personal_stress = 0.9;
    fearful.trauma_level = TraumaLevel::Paranoid;
    fearful.desperation_index = 0.7;
    NPC skeptic;
    skeptic.entity_id = "skeptic";
    skeptic.district_id = "shared";
    skeptic.personal_stress = 0.05;
    skeptic.relationships["deceased"] = -0.8;
    NPC close_friend;
    close_friend.entity_id = "close-friend";
    close_friend.district_id = "shared";
    close_friend.personal_stress = 0.1;
    close_friend.relationships["deceased"] = 0.95;
    NPCMemory trusted_history;
    trusted_history.target_entity_id = "deceased";
    trusted_history.retention = 0.95;
    trusted_history.action_tag = ActionTag::InteractionPolite;
    close_friend.memories.push_back(trusted_history);
    interpretation_state.npcs = {fearful, skeptic, close_friend};
    SimulationWorld interpretation_world(std::move(interpretation_state), 0.0, 9U);
    LifeCoordinator& interpretation_life = interpretation_world.life_system();
    interpretation_life.register_character("deceased");
    assert(interpretation_life.kill("deceased", 0U, "illness"));
    assert(interpretation_life.enter_ghost("deceased"));
    interpretation_life.set_ghost_windows({GhostTimeWindow{8.0, 10.0, 1.0}});
    (void)interpretation_world.advance(8.5);
    const auto fearful_sound = interpretation_world.attempt_ghost_influence("deceased", "fearful", "sound", 9.0);
    const auto skeptic_sound = interpretation_world.attempt_ghost_influence("deceased", "skeptic", "sound", 9.0);
    const auto friend_sound = interpretation_world.attempt_ghost_influence("deceased", "close-friend", "sound", 9.0);
    assert(fearful_sound.accepted && skeptic_sound.accepted && friend_sound.accepted);
    const auto& interpreted = interpretation_world.state().npcs;
    assert(interpreted[0].personal_stress > interpreted[2].personal_stress);
    assert(interpreted[0].personal_stress > interpreted[1].personal_stress);
    assert(interpreted[2].goals.end() != std::find(interpreted[2].goals.begin(), interpreted[2].goals.end(), "seek_ghost_contact"));
    assert(interpreted[0].goals.end() == std::find(interpreted[0].goals.begin(), interpreted[0].goals.end(), "seek_ghost_contact"));

    // Repeated events accumulate history-dependent behaviour and relationships.
    const double friend_tie_after_first = interpreted[2].relationships.at("deceased");
    (void)interpretation_world.advance(24.0);
    auto repeat_friend_sound = interpretation_world.attempt_ghost_influence("deceased", "close-friend", "sound", 9.0);
    for (int attempt = 0; attempt < 20 && !repeat_friend_sound.accepted; ++attempt) {
        repeat_friend_sound = interpretation_world.attempt_ghost_influence(
            "deceased", "close-friend", "sound", 9.0);
    }
    assert(repeat_friend_sound.accepted);
    assert(interpretation_world.state().npcs[2].relationships.at("deceased") >= friend_tie_after_first);
    assert(interpretation_world.state().npcs[2].goals.end() != std::find(
        interpretation_world.state().npcs[2].goals.begin(), interpretation_world.state().npcs[2].goals.end(),
        "seek_ghost_contact"));

    // Lifecycle state survives the versioned binary world snapshot.
    SimulationWorld lifecycle_save_world;
    LifeCoordinator& saved_life = lifecycle_save_world.life_system();
    saved_life.register_character("persistent-life");
    MedicalCondition persistent_condition;
    persistent_condition.condition_id = "long-injury";
    persistent_condition.severity = 0.65;
    persistent_condition.recovery_per_day = 0.08;
    persistent_condition.lasting_impairment = true;
    persistent_condition.impairment_floor = 0.12;
    saved_life.add_condition("persistent-life", persistent_condition);
    MedicalTreatment persistent_treatment;
    persistent_treatment.treatment_id = "rehab";
    persistent_treatment.condition_id = "long-injury";
    persistent_treatment.effectiveness = 0.25;
    persistent_treatment.daily_cost = 3.5;
    persistent_treatment.complication_risk = 0.1;
    saved_life.add_treatment("persistent-life", persistent_treatment);
    saved_life.add_obligation(LifeObligation{
        "unpaid-debt", "persistent-life", "creditor", 42.5, 17U, false, false});
    saved_life.set_ghost_windows({GhostTimeWindow{1.5, 3.5, 0.7}});
    assert(saved_life.kill("persistent-life", 4U, "complications"));
    assert(saved_life.enter_ghost("persistent-life"));
    std::stringstream lifecycle_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(lifecycle_save_world, lifecycle_snapshot);
    lifecycle_snapshot.seekg(0);
    SimulationWorld lifecycle_restored = load_world(lifecycle_snapshot);
    const auto& restored_life = lifecycle_restored.life_system();
    assert(restored_life.characters().size() == 1);
    const LifeCharacter& restored_character = restored_life.characters().at("persistent-life");
    assert(restored_character.status == LifeStatus::Ghost);
    assert(restored_character.death_day == 4U);
    assert(restored_character.death_cause == "complications");
    assert(restored_character.conditions.size() == 1);
    assert(restored_character.conditions[0].severity == 0.65);
    assert(restored_character.conditions[0].lasting_impairment);
    assert(restored_character.conditions[0].impairment_floor == 0.12);
    assert(restored_character.treatments.size() == 1);
    assert(restored_character.treatments[0].daily_cost == 3.5);
    assert(restored_character.treatments[0].complication_risk == 0.1);
    assert(restored_life.obligations().size() == 1);
    assert(restored_life.obligations()[0].obligation_id == "unpaid-debt");
    assert(restored_life.obligations()[0].amount_due == 42.5);
    assert(restored_life.obligations()[0].due_day == 17U);
    assert(restored_life.ghost_windows().size() == 1);
    assert(restored_life.ghost_windows()[0].start_hour == 1.5);
    assert(restored_life.ghost_windows()[0].end_hour == 3.5);
    assert(restored_life.ghost_windows()[0].strength == 0.7);
    assert(restored_life.ghost_windows()[0].permitted_actions
        == std::vector<std::string>({"sign", "sound", "dream"}));

    // Campaign-level save/resume remains identical after death, debt settlement,
    // ghost-window decisions, and the transition into a new archived timeline.
    WorldState campaign_state;
    NPC former_player;
    former_player.entity_id = "former-player";
    former_player.money = 20.0;
    NPC creditor;
    creditor.entity_id = "creditor";
    creditor.money = 0.0;
    NPC ghost_supporter;
    ghost_supporter.entity_id = "ghost_supporter";
    ghost_supporter.money = 100.0;
    ghost_supporter.relationships["former-player"] = 0.9;
    NPC ghost_listener;
    ghost_listener.entity_id = "ghost_listener";
    ghost_listener.personal_stress = 0.2;
    ghost_listener.isolation = 0.4;
    ghost_listener.social_need = 0.5;
    NPCMemory remembered_ghost;
    remembered_ghost.witness_id = "ghost_supporter";
    remembered_ghost.target_entity_id = "former-player";
    remembered_ghost.retention = 0.9;
    remembered_ghost.action_tag = ActionTag::InteractionPolite;
    ghost_supporter.memories.push_back(remembered_ghost);
    campaign_state.npcs = {former_player, creditor, ghost_supporter, ghost_listener};

    CampaignCoordinator campaign(SimulationWorld(std::move(campaign_state), 0.0, 987U));
    campaign.begin_first_life("former-player");
    campaign.active_world().life_system().add_obligation(
        LifeObligation{"family-debt", "former-player", "creditor", 40.0, 30U, false, false});
    campaign.active_world().life_system().set_ghost_windows({GhostTimeWindow{8.0, 10.0, 1.0}});
    assert(campaign.record_death("complications"));
    assert(campaign.enter_ghost());

    CampaignCoordinator uninterrupted = campaign;
    CampaignCoordinator save_resume = campaign;
    (void)uninterrupted.advance(8.5);
    (void)save_resume.advance(8.5);
    std::stringstream campaign_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_campaign(save_resume, campaign_snapshot);
    campaign_snapshot.seekg(0);
    save_resume = load_campaign(campaign_snapshot);

    const GhostInfluenceResult uninterrupted_influence =
        uninterrupted.attempt_ghost_influence("ghost_supporter", "sound", 9.0);
    const GhostInfluenceResult resumed_influence =
        save_resume.attempt_ghost_influence("ghost_supporter", "sound", 9.0);
    assert(uninterrupted_influence.accepted == resumed_influence.accepted);
    assert(uninterrupted_influence.score == resumed_influence.score);
    assert(uninterrupted_influence.accepted);
    assert(uninterrupted.active_world().random_state() == save_resume.active_world().random_state());
    assert(uninterrupted.active_world().state().ongoing_events.size()
        == save_resume.active_world().state().ongoing_events.size());
    assert(!uninterrupted.active_world().state().ongoing_events.empty());
    const OngoingEvent& ghost_event =
        uninterrupted.active_world().state().ongoing_events.back();
    assert(ghost_event.event_id.find("ghost-influence:") == 0U);
    assert(ghost_event.actor_id == "former-player");
    assert(ghost_event.witness_ids == std::vector<EntityId>({"ghost_supporter"}));
    assert(ghost_event.resolved);
    assert(ghost_event.created_hour == 9.0);
    assert(ghost_event.action_tag == ActionTag::GhostSound);
    assert(uninterrupted.active_world().state().npcs[2].personal_stress
        == save_resume.active_world().state().npcs[2].personal_stress);
    const auto& reference_memories = uninterrupted.active_world().state().npcs[2].memories;
    const auto& resumed_memories = save_resume.active_world().state().npcs[2].memories;
    assert(reference_memories.size() == resumed_memories.size());
    assert(reference_memories.back().action_tag == ActionTag::GhostSound);
    assert(reference_memories.back().timestamp_hour == ghost_event.created_hour);
    assert(reference_memories.back().target_entity_id == "former-player");
    assert(reference_memories.back().retention == resumed_memories.back().retention);

    // Relationship, goal, and emotional consequences are all replay-stable.
    assert(uninterrupted.active_world().state().npcs[2].goals
        == save_resume.active_world().state().npcs[2].goals);
    assert(uninterrupted.active_world().state().npcs[2].relationships
        == save_resume.active_world().state().npcs[2].relationships);
    assert(uninterrupted.active_world().state().npcs[2].personal_stress
        == save_resume.active_world().state().npcs[2].personal_stress);
    const double listener_stress_before = uninterrupted.active_world().state().npcs[3].personal_stress;
    const Conversation ghost_story = uninterrupted.active_world().talk("ghost_listener", "ghost_supporter");
    const Conversation resumed_ghost_story = save_resume.active_world().talk("ghost_listener", "ghost_supporter");
    const auto heard_ghost_sound = [](const Conversation& story) {
        return std::any_of(story.transferred.begin(), story.transferred.end(),
            [](const Rumour& rumour) { return rumour.action_tag == "Ghost.Sound"; });
    };
    assert(heard_ghost_sound(ghost_story) && heard_ghost_sound(resumed_ghost_story));
    const double listener_stress_after_first_telling =
        uninterrupted.active_world().state().npcs[3].personal_stress;
    const double resumed_listener_stress_after_first_telling =
        save_resume.active_world().state().npcs[3].personal_stress;
    assert(listener_stress_after_first_telling >= listener_stress_before + 0.018);
    assert(listener_stress_after_first_telling == resumed_listener_stress_after_first_telling);
    const double listener_isolation_after_first_telling =
        uninterrupted.active_world().state().npcs[3].isolation;
    (void)uninterrupted.active_world().talk("ghost_listener", "ghost_supporter");
    (void)save_resume.active_world().talk("ghost_listener", "ghost_supporter");
    assert(std::abs(uninterrupted.active_world().state().npcs[3].personal_stress
        - listener_stress_after_first_telling - 0.01) < 1e-9);
    assert(uninterrupted.active_world().state().npcs[3].personal_stress
        == save_resume.active_world().state().npcs[3].personal_stress);
    assert(uninterrupted.active_world().state().npcs[3].isolation == listener_isolation_after_first_telling);
    assert(uninterrupted.active_world().state().npcs[3].isolation
        == save_resume.active_world().state().npcs[3].isolation);

    const GhostInfluenceResult uninterrupted_forbidden =
        uninterrupted.attempt_ghost_influence("ghost_supporter", "comfort", 9.0);
    const GhostInfluenceResult resumed_forbidden =
        save_resume.attempt_ghost_influence("ghost_supporter", "comfort", 9.0);
    assert(!uninterrupted_forbidden.accepted && !resumed_forbidden.accepted);
    assert(uninterrupted_forbidden.reason == resumed_forbidden.reason);
    assert(!uninterrupted.attempt_ghost_influence("ghost_supporter", "sound", 12.0).accepted);
    assert(!save_resume.attempt_ghost_influence("ghost_supporter", "sound", 12.0).accepted);

    (void)uninterrupted.advance(15.5);
    (void)save_resume.advance(15.5);
    const auto& reference_obligation = uninterrupted.active_world().life_system().obligations().at(0);
    const auto& resumed_obligation = save_resume.active_world().life_system().obligations().at(0);
    assert(reference_obligation.settled && resumed_obligation.settled);
    assert(reference_obligation.amount_due == resumed_obligation.amount_due);
    assert(uninterrupted.active_world().state().npcs[1].money ==
        save_resume.active_world().state().npcs[1].money);
    assert(uninterrupted.active_world().state().npcs[2].money ==
        save_resume.active_world().state().npcs[2].money);
    assert(uninterrupted.active_world().state().npcs[0].money ==
        save_resume.active_world().state().npcs[0].money);
    assert(uninterrupted.active_world().life_system().characters().at("former-player").status ==
        save_resume.active_world().life_system().characters().at("former-player").status);
    std::stringstream reference_bytes(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream resumed_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_campaign(uninterrupted, reference_bytes);
    save_campaign(save_resume, resumed_bytes);
    assert(reference_bytes.str() == resumed_bytes.str());

    // Replay across multiple days and save points. Each resumed branch must
    // produce the same next ghost decision, memory/event effects, and final bytes.
    for (int checkpoint_day = 1; checkpoint_day <= 3; ++checkpoint_day) {
        (void)uninterrupted.advance(24.0);
        (void)save_resume.advance(24.0);
        std::stringstream checkpoint_bytes(std::ios::in | std::ios::out | std::ios::binary);
        save_campaign(save_resume, checkpoint_bytes);
        checkpoint_bytes.seekg(0);
        save_resume = load_campaign(checkpoint_bytes);

        const GhostInfluenceResult next_reference =
            uninterrupted.attempt_ghost_influence("ghost_supporter", "dream", 9.0);
        const GhostInfluenceResult next_resumed =
            save_resume.attempt_ghost_influence("ghost_supporter", "dream", 9.0);
        assert(next_reference.accepted == next_resumed.accepted);
        assert(next_reference.score == next_resumed.score);
        assert(uninterrupted.active_world().random_state() == save_resume.active_world().random_state());
        const WorldState& reference_state = uninterrupted.active_world().state();
        const WorldState& resumed_state = save_resume.active_world().state();
        assert(reference_state.ongoing_events.size() == resumed_state.ongoing_events.size());
        assert(!reference_state.ongoing_events.empty());
        const OngoingEvent& latest_ghost_event = reference_state.ongoing_events.back();
        const auto latest_manifestation_memory = std::find_if(
            reference_state.npcs[2].memories.rbegin(), reference_state.npcs[2].memories.rend(),
            [&latest_ghost_event](const NPCMemory& memory) {
                return memory.target_entity_id == latest_ghost_event.actor_id
                    && memory.action_tag == latest_ghost_event.action_tag;
            });
        assert(latest_manifestation_memory != reference_state.npcs[2].memories.rend());
        assert(latest_manifestation_memory->timestamp_hour == latest_ghost_event.created_hour);
        assert(reference_state.npcs[2].memories.size() == resumed_state.npcs[2].memories.size());
        assert(reference_state.npcs[2].isolation == resumed_state.npcs[2].isolation);
        assert(reference_state.npcs[2].social_need == resumed_state.npcs[2].social_need);
        assert(reference_state.npcs[2].personal_stress == resumed_state.npcs[2].personal_stress);

        std::stringstream checkpoint_reference(std::ios::in | std::ios::out | std::ios::binary);
        std::stringstream checkpoint_resumed(std::ios::in | std::ios::out | std::ios::binary);
        save_campaign(uninterrupted, checkpoint_reference);
        save_campaign(save_resume, checkpoint_resumed);
        assert(checkpoint_reference.str() == checkpoint_resumed.str());
    }

    uninterrupted.start_new_life("next-life", WorldState{}, 123U);
    save_resume.start_new_life("next-life", WorldState{}, 123U);
    assert(uninterrupted.archives().size() == 1U);
    assert(save_resume.archives().size() == 1U);
    assert(uninterrupted.active_world().total_hours() == 0.0);
    assert(uninterrupted.active_world().day_index() == 0U);
    assert(uninterrupted.active_character_id() == "next-life");
    const SimulationWorld archived_timeline =
        uninterrupted.inspect_archive(uninterrupted.archives().front().archive_id);
    assert(archived_timeline.life_system().characters().at("former-player").status == LifeStatus::Archived);
    assert(archived_timeline.life_system().obligations().at(0).settled);
    std::stringstream final_campaign_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_campaign(uninterrupted, final_campaign_snapshot);
    final_campaign_snapshot.seekg(0);
    CampaignCoordinator final_campaign_restored = load_campaign(final_campaign_snapshot);
    assert(final_campaign_restored.archives().size() == 1U);
    assert(final_campaign_restored.active_world().total_hours() == 0.0);
    assert(final_campaign_restored.active_character_id() == "next-life");
    std::stringstream final_bytes_a(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream final_bytes_b(std::ios::in | std::ios::out | std::ios::binary);
    save_campaign(uninterrupted, final_bytes_a);
    save_campaign(final_campaign_restored, final_bytes_b);
    assert(final_bytes_a.str() == final_bytes_b.str());

    // Long-term belief confidence changes at deterministic rates: first-hand and
    // corroborated accounts persist better, while unresolved conflicting accounts
    // fade faster. Save/resume must preserve the exact daily progression.
    WorldState belief_decay_state;
    NPC direct_observer;
    direct_observer.entity_id = "direct-observer";
    direct_observer.beliefs.push_back(NPCBelief{
        "target", ActionTag::SocialAid, 0.0, 0.8, "direct-observer", true, 0U, 0U});
    NPC corroborated_listener;
    corroborated_listener.entity_id = "corroborated-listener";
    corroborated_listener.beliefs.push_back(NPCBelief{
        "target", ActionTag::SocialAid, 0.0, 0.8, "speaker", false, 4U, 0U});
    NPC decay_hearsay_npc;
    decay_hearsay_npc.entity_id = "hearsay-listener";
    decay_hearsay_npc.beliefs.push_back(NPCBelief{
        "target", ActionTag::SocialAid, 0.0, 0.8, "speaker", false, 0U, 0U});
    NPC disputed_listener;
    disputed_listener.entity_id = "disputed-listener";
    disputed_listener.beliefs.push_back(NPCBelief{
        "target", ActionTag::SocialAid, 0.0, 0.8, "speaker", false, 0U, 3U});
    belief_decay_state.npcs = {
        direct_observer, corroborated_listener, decay_hearsay_npc, disputed_listener};
    SimulationWorld belief_decay_world(belief_decay_state, 0.0, 441U);
    SimulationWorld belief_decay_resumed(belief_decay_state, 0.0, 441U);
    (void)belief_decay_world.advance(24.0);
    (void)belief_decay_resumed.advance(24.0);
    const auto& decayed_beliefs = belief_decay_world.state().npcs;
    assert(decayed_beliefs[0].beliefs[0].confidence < 0.8);
    assert(decayed_beliefs[0].beliefs[0].confidence
        > decayed_beliefs[2].beliefs[0].confidence);
    assert(decayed_beliefs[1].beliefs[0].confidence
        > decayed_beliefs[0].beliefs[0].confidence);
    assert(decayed_beliefs[3].beliefs[0].confidence
        < decayed_beliefs[2].beliefs[0].confidence);
    std::stringstream decay_reference(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream decay_resumed_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_world(belief_decay_world, decay_reference);
    save_world(belief_decay_resumed, decay_resumed_bytes);
    assert(decay_reference.str() == decay_resumed_bytes.str());

    // A save point between days does not change confidence or serialized world state.
    (void)belief_decay_world.advance(24.0);
    (void)belief_decay_resumed.advance(24.0);
    std::stringstream decay_checkpoint(std::ios::in | std::ios::out | std::ios::binary);
    save_world(belief_decay_resumed, decay_checkpoint);
    decay_checkpoint.seekg(0);
    belief_decay_resumed = load_world(decay_checkpoint);
    (void)belief_decay_resumed.advance(24.0);
    (void)belief_decay_world.advance(24.0);
    std::stringstream decay_continuous_bytes(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream decay_replayed_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_world(belief_decay_world, decay_continuous_bytes);
    save_world(belief_decay_resumed, decay_replayed_bytes);
    assert(decay_continuous_bytes.str() == decay_replayed_bytes.str());

    // Direct observation challenges conflicting hearsay about the same event,
    // without erasing either account. The revision survives persistence exactly.
    WorldState direct_evidence_state;
    NPC direct_evidence_observer;
    direct_evidence_observer.entity_id = "direct-evidence-observer";
    direct_evidence_observer.district_id = "evidence-district";
    direct_evidence_observer.beliefs.push_back(NPCBelief{
        "evidence-target", ActionTag::CrimeAssault, 0.0, 0.72,
        "rumour-source", false, 1U, 0U});
    NPC evidence_target;
    evidence_target.entity_id = "evidence-target";
    evidence_target.district_id = "evidence-district";
    direct_evidence_state.npcs = {direct_evidence_observer, evidence_target};
    SimulationWorld direct_evidence_world(direct_evidence_state, 0.0, 882U);
    Description evidence_description;
    evidence_description.height_m = 1.8;
    assert(direct_evidence_world.record_witnessed_action(
        "evidence-target", ActionTag::CrimeTheft, evidence_description,
        {"direct-evidence-observer"}) == 1U);
    const NPC& revised_observer = direct_evidence_world.state().npcs[0];
    assert(revised_observer.beliefs.size() == 2U);
    assert(revised_observer.beliefs[0].action_tag == ActionTag::CrimeAssault);
    assert(revised_observer.beliefs[0].confidence < 0.72);
    assert(revised_observer.beliefs[0].contradictions == 1U);
    assert(revised_observer.beliefs[1].action_tag == ActionTag::CrimeTheft);
    assert(revised_observer.beliefs[1].directly_observed);
    assert(revised_observer.beliefs[1].confidence == 1.0);
    std::stringstream direct_evidence_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_world(direct_evidence_world, direct_evidence_bytes);
    direct_evidence_bytes.seekg(0);
    SimulationWorld direct_evidence_resumed = load_world(direct_evidence_bytes);
    assert(direct_evidence_resumed.state().npcs[0].beliefs.size() == 2U);
    assert(direct_evidence_resumed.state().npcs[0].beliefs[0].confidence
        == revised_observer.beliefs[0].confidence);
    assert(direct_evidence_resumed.state().npcs[0].beliefs[0].contradictions == 1U);
    std::stringstream direct_evidence_original(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream direct_evidence_loaded(std::ios::in | std::ios::out | std::ios::binary);
    save_world(direct_evidence_world, direct_evidence_original);
    save_world(direct_evidence_resumed, direct_evidence_loaded);
    assert(direct_evidence_original.str() == direct_evidence_loaded.str());


    // Repetition from one speaker is not independent corroboration. It must not
    // inflate belief confidence/counts or repeatedly weaken a competing account.
    WorldState repeated_rumour_state;
    NPC repeated_rumour_speaker;
    repeated_rumour_speaker.entity_id = "repeat-speaker";
    repeated_rumour_speaker.district_id = "rumour-district";
    NPCMemory repeated_theft_memory;
    repeated_theft_memory.witness_id = "repeat-speaker";
    repeated_theft_memory.target_entity_id = "rumour-target";
    repeated_theft_memory.initial_impact = 0.8;
    repeated_theft_memory.retention = 0.8;
    repeated_theft_memory.timestamp_hour = 0.0;
    repeated_theft_memory.action_tag = ActionTag::CrimeTheft;
    repeated_rumour_speaker.memories.push_back(repeated_theft_memory);
    NPC repeated_rumour_listener;
    repeated_rumour_listener.entity_id = "repeat-listener";
    repeated_rumour_listener.district_id = "rumour-district";
    repeated_rumour_listener.beliefs.push_back(NPCBelief{
        "rumour-target", ActionTag::CrimeAssault, 0.0, 0.7,
        "other-source", false, 1U, 0U});
    NPC rumour_target;
    rumour_target.entity_id = "rumour-target";
    rumour_target.district_id = "rumour-district";
    repeated_rumour_state.npcs = {repeated_rumour_speaker, repeated_rumour_listener, rumour_target};
    SimulationWorld repeated_rumour_world(repeated_rumour_state, 0.0, 991U);
    SimulationWorld repeated_rumour_resumed(repeated_rumour_state, 0.0, 991U);
    (void)repeated_rumour_world.talk("repeat-listener", "repeat-speaker");
    (void)repeated_rumour_resumed.talk("repeat-listener", "repeat-speaker");
    const auto get_belief = [](const NPC& npc, ActionTag tag) -> const NPCBelief& {
        const auto found = std::find_if(npc.beliefs.begin(), npc.beliefs.end(),
            [tag](const NPCBelief& candidate) { return candidate.action_tag == tag; });
        assert(found != npc.beliefs.end());
        return *found;
    };
    const NPCBelief first_telling = get_belief(
        repeated_rumour_world.state().npcs[1], ActionTag::CrimeTheft);
    const double first_telling_confidence = first_telling.confidence;
    const std::uint32_t first_telling_corroborations = first_telling.corroborations;
    const double competing_confidence_after_first =
        get_belief(repeated_rumour_world.state().npcs[1], ActionTag::CrimeAssault).confidence;
    (void)repeated_rumour_world.talk("repeat-listener", "repeat-speaker");
    (void)repeated_rumour_resumed.talk("repeat-listener", "repeat-speaker");
    const NPC& repeated_listener = repeated_rumour_world.state().npcs[1];
    const NPCBelief& repeated_theft_belief = get_belief(repeated_listener, ActionTag::CrimeTheft);
    const NPCBelief& repeated_assault_belief = get_belief(repeated_listener, ActionTag::CrimeAssault);
    assert(repeated_theft_belief.source_entity_id == "repeat-speaker");
    assert(repeated_theft_belief.confidence == first_telling_confidence);
    assert(repeated_theft_belief.corroborations == first_telling_corroborations);
    assert(repeated_assault_belief.confidence == competing_confidence_after_first);
    assert(repeated_assault_belief.contradictions == 1U);
    std::stringstream repeated_rumour_bytes(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream repeated_rumour_resumed_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_world(repeated_rumour_world, repeated_rumour_bytes);
    save_world(repeated_rumour_resumed, repeated_rumour_resumed_bytes);
    assert(repeated_rumour_bytes.str() == repeated_rumour_resumed_bytes.str());


    // Confidence about unrelated events must not change a source's reliability
    // for the specific story being passed on.
    WorldState claim_reliability_state;
    NPC low_unrelated_source;
    low_unrelated_source.entity_id = "low-unrelated-source";
    low_unrelated_source.district_id = "claim-reliability-district";
    NPCMemory low_source_story;
    low_source_story.witness_id = low_unrelated_source.entity_id;
    low_source_story.target_entity_id = "claim-target-a";
    low_source_story.action_tag = ActionTag::CrimeTheft;
    low_source_story.timestamp_hour = 0.0;
    low_source_story.retention = 0.8;
    low_unrelated_source.memories.push_back(low_source_story);
    low_unrelated_source.beliefs.push_back(NPCBelief{
        "unrelated-target-a", ActionTag::CrimeAssault, 0.0, 0.1,
        "other-source", false, 0U, 0U});
    NPC high_unrelated_source = low_unrelated_source;
    high_unrelated_source.entity_id = "high-unrelated-source";
    high_unrelated_source.memories.front().witness_id = high_unrelated_source.entity_id;
    high_unrelated_source.memories.front().target_entity_id = "claim-target-b";
    high_unrelated_source.beliefs.front().target_entity_id = "unrelated-target-b";
    high_unrelated_source.beliefs.front().confidence = 0.9;
    NPC claim_listener_a;
    claim_listener_a.entity_id = "claim-listener-a";
    claim_listener_a.district_id = "claim-reliability-district";
    NPC claim_listener_b = claim_listener_a;
    claim_listener_b.entity_id = "claim-listener-b";
    NPC claim_target_a;
    claim_target_a.entity_id = "claim-target-a";
    claim_target_a.district_id = "claim-reliability-district";
    NPC claim_target_b = claim_target_a;
    claim_target_b.entity_id = "claim-target-b";
    claim_reliability_state.npcs = {low_unrelated_source, high_unrelated_source,
        claim_listener_a, claim_listener_b, claim_target_a, claim_target_b};
    SimulationWorld claim_reliability_world(claim_reliability_state, 0.0, 178U);
    (void)claim_reliability_world.talk("claim-listener-a", "low-unrelated-source");
    (void)claim_reliability_world.talk("claim-listener-b", "high-unrelated-source");
    const auto claim_confidence = [](const NPC& npc, const std::string& target_id) {
        const auto found = std::find_if(npc.beliefs.begin(), npc.beliefs.end(),
            [&target_id](const NPCBelief& belief) {
                return belief.target_entity_id == target_id
                    && belief.action_tag == ActionTag::CrimeTheft;
            });
        assert(found != npc.beliefs.end());
        return found->confidence;
    };
    assert(claim_confidence(claim_reliability_world.state().npcs[2], "claim-target-a")
        == claim_confidence(claim_reliability_world.state().npcs[3], "claim-target-b"));

    // Stable personality traits bias second-hand interpretation without changing
    // the event record or consuming randomness; save/resume preserves the traits.
    WorldState bias_state;
    NPC bias_speaker;
    bias_speaker.entity_id = "bias-speaker";
    bias_speaker.district_id = "D-bias";
    NPCMemory theft_story;
    theft_story.witness_id = "bias-speaker";
    theft_story.target_entity_id = "bias-target";
    theft_story.action_tag = ActionTag::CrimeTheft;
    theft_story.timestamp_hour = 0.0;
    theft_story.retention = 0.9;
    bias_speaker.memories.push_back(theft_story);
    NPC loyal_listener;
    loyal_listener.entity_id = "loyal-listener";
    loyal_listener.district_id = "D-bias";
    loyal_listener.loyalty_bias = 1.0;
    loyal_listener.relationships["bias-target"] = 0.9;
    NPC skeptical_listener = loyal_listener;
    skeptical_listener.entity_id = "skeptical-listener";
    skeptical_listener.loyalty_bias = 0.5;
    skeptical_listener.skepticism = 1.0;
    bias_state.npcs = {bias_speaker, loyal_listener, skeptical_listener};
    SimulationWorld bias_world(bias_state, 0.0, 177U);
    (void)bias_world.talk("loyal-listener", "bias-speaker");
    (void)bias_world.talk("skeptical-listener", "bias-speaker");
    const auto confidence_for = [](const NPC& npc) {
        const auto found = std::find_if(npc.beliefs.begin(), npc.beliefs.end(),
            [](const NPCBelief& belief) { return belief.action_tag == ActionTag::CrimeTheft; });
        assert(found != npc.beliefs.end());
        return found->confidence;
    };
    assert(confidence_for(bias_world.state().npcs[1])
        > confidence_for(bias_world.state().npcs[2]));
    std::stringstream bias_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(bias_world, bias_snapshot);
    bias_snapshot.seekg(0);
    SimulationWorld bias_restored = load_world(bias_snapshot);
    assert(bias_restored.state().npcs[1].loyalty_bias == 1.0);
    assert(bias_restored.state().npcs[2].skepticism == 1.0);
    std::stringstream bias_bytes_a(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream bias_bytes_b(std::ios::in | std::ios::out | std::ios::binary);
    save_world(bias_world, bias_bytes_a);
    save_world(bias_restored, bias_bytes_b);
    assert(bias_bytes_a.str() == bias_bytes_b.str());


    // The same trade-off is scored differently by NPCs with different values.
    NPC urgency_focused;
    urgency_focused.entity_id = "urgency-focused";
    urgency_focused.compassion = 1.0;
    urgency_focused.fairness_value = 0.1;
    urgency_focused.safety_value = 0.2;
    urgency_focused.freedom_value = 0.2;
    urgency_focused.self_interest_value = 0.1;
    NPC fairness_focused = urgency_focused;
    fairness_focused.entity_id = "fairness-focused";
    fairness_focused.compassion = 0.1;
    fairness_focused.fairness_value = 1.0;
    fairness_focused.safety_value = 0.2;
    fairness_focused.freedom_value = 0.2;
    fairness_focused.self_interest_value = 0.1;
    const MoralChoiceOption urgent_aid{"urgent-aid", 1.0, 0.4, 0.2, 0.4, 0.3, 0.8, 0.8};
    const MoralChoiceOption fair_distribution{"fair-distribution", 0.4, 0.7, 1.0, 0.5, 0.5, 0.2, 0.2};
    assert(evaluate_moral_choice(urgency_focused, urgent_aid).score
        > evaluate_moral_choice(urgency_focused, fair_distribution).score);
    assert(evaluate_moral_choice(fairness_focused, urgent_aid).score
        < evaluate_moral_choice(fairness_focused, fair_distribution).score);
    assert(evaluate_moral_choice(fairness_focused, fair_distribution).score
        == evaluate_moral_choice(fairness_focused, fair_distribution).score);
    const MoralChoiceExplanation urgent_explanation =
        explain_moral_choice(urgency_focused, urgent_aid);
    assert(urgent_explanation.option_id == urgent_aid.option_id);
    assert(urgent_explanation.factors.size() == 7U);
    assert(urgent_explanation.factors[0].factor == "urgency");
    assert(urgent_explanation.factors[0].npc_value == 1.0);
    assert(urgent_explanation.factors[0].option_value == 1.0);
    assert(std::abs(urgent_explanation.factors[0].contribution - 0.25) < 1e-12);
    double explained_score = 0.0;
    for (const MoralChoiceFactorExplanation& factor : urgent_explanation.factors) {
        explained_score += factor.contribution;
    }
    assert(std::abs(explained_score - urgent_explanation.total_score) < 1e-12);
    assert(urgent_explanation.total_score
        == evaluate_moral_choice(urgency_focused, urgent_aid).score);
    NPC out_of_range_values = urgency_focused;
    out_of_range_values.compassion = 2.0;
    MoralChoiceOption out_of_range_option = urgent_aid;
    out_of_range_option.urgency = 2.0;
    const MoralChoiceExplanation clamped_explanation =
        explain_moral_choice(out_of_range_values, out_of_range_option);
    assert(clamped_explanation.factors.front().npc_value == 1.0);
    assert(clamped_explanation.factors.front().option_value == 1.0);
    std::stringstream moral_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    WorldState moral_state;
    fairness_focused.fairness_value = 1.0;
    fairness_focused.safety_value = 0.8;
    fairness_focused.freedom_value = 0.3;
    fairness_focused.self_interest_value = 0.7;
    moral_state.npcs.push_back(fairness_focused);
    SimulationWorld moral_world(moral_state, 0.0, 181U);
    save_world(moral_world, moral_snapshot);
    moral_snapshot.seekg(0);
    SimulationWorld moral_restored = load_world(moral_snapshot);
    assert(moral_restored.state().npcs.front().fairness_value == 1.0);
    assert(moral_restored.state().npcs.front().safety_value == 0.8);
    assert(moral_restored.state().npcs.front().freedom_value == 0.3);
    assert(moral_restored.state().npcs.front().self_interest_value == 0.7);


    const MoralChoiceEvaluation preferred_urgent = choose_moral_option(
        urgency_focused, {urgent_aid, fair_distribution});
    const MoralChoiceEvaluation preferred_fair = choose_moral_option(
        fairness_focused, {urgent_aid, fair_distribution});
    assert(preferred_urgent.option_id == "urgent-aid");
    assert(preferred_fair.option_id == "fair-distribution");
    const MoralChoiceOption tied_a{"first", 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
    const MoralChoiceOption tied_b{"second", 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
    assert(choose_moral_option(NPC{}, {tied_a, tied_b}).option_id == "first");
    bool rejected_empty_moral_options = false;
    try {
        (void)choose_moral_option(NPC{}, {});
    } catch (const std::invalid_argument&) {
        rejected_empty_moral_options = true;
    }
    assert(rejected_empty_moral_options);

    // Moral decisions apply only scenario-authored effects for the selected
    // option; bounds and reported deltas match the actual state changes.
    NPC dilemma_npc;
    dilemma_npc.entity_id = "dilemma-npc";
    dilemma_npc.money = 5.0;
    dilemma_npc.personal_stress = 0.9;
    dilemma_npc.relationships["neighbor"] = 0.8;
    const auto dilemma_result = resolve_moral_choice(
        dilemma_npc, {urgent_aid, fair_distribution},
        {{"urgent-aid", -8.0, 0.3, {{"neighbor", 0.5}, {"stranger", -0.4}}},
         {"fair-distribution", 2.0, -0.2, {{"neighbor", -0.2}}}});
    assert(dilemma_result.choice.option_id == "fair-distribution");
    assert(dilemma_npc.money == 7.0);
    assert(std::abs(dilemma_npc.personal_stress - 0.7) < 1e-9);
    assert(std::abs(dilemma_npc.relationships["neighbor"] - 0.6) < 1e-9);
    assert(dilemma_npc.relationships.find("stranger") == dilemma_npc.relationships.end());
    assert(std::abs(dilemma_result.money_delta_applied - 2.0) < 1e-9);
    assert(std::abs(dilemma_result.stress_delta_applied + 0.2) < 1e-9);
    assert(std::abs(dilemma_result.relationship_deltas_applied.at("neighbor") + 0.2) < 1e-9);

    NPC constrained_npc;
    constrained_npc.money = 1.0;
    constrained_npc.personal_stress = 0.95;
    constrained_npc.relationships["neighbor"] = 0.9;
    const auto constrained_result = resolve_moral_choice(
        constrained_npc, {urgent_aid},
        {{"urgent-aid", -10.0, 0.5, {{"neighbor", 0.5}}}});
    assert(constrained_npc.money == 0.0);
    assert(constrained_npc.personal_stress == 1.0);
    assert(constrained_npc.relationships["neighbor"] == 1.0);
    assert(constrained_result.money_delta_applied == -1.0);
    assert(std::abs(constrained_result.stress_delta_applied - 0.05) < 1e-9);
    assert(std::abs(constrained_result.relationship_deltas_applied.at("neighbor") - 0.1) < 1e-9);

    bool rejected_duplicate_options = false;
    NPC invalid_scenario_npc;
    try {
        (void)resolve_moral_choice(invalid_scenario_npc, {urgent_aid, urgent_aid}, {});
    } catch (const std::invalid_argument&) {
        rejected_duplicate_options = true;
    }
    assert(rejected_duplicate_options);
    bool rejected_unknown_consequence = false;
    try {
        (void)resolve_moral_choice(invalid_scenario_npc, {urgent_aid},
            {{"not-an-option", 1.0, 0.0, {}}});
    } catch (const std::invalid_argument&) {
        rejected_unknown_consequence = true;
    }
    assert(rejected_unknown_consequence);


    // Direct witness observations enter the world-owned provenance ledger.
    WorldState witnessed_information_state;
    NPC witnessed_actor;
    witnessed_actor.entity_id = "observed-actor";
    witnessed_actor.district_id = "observed-district";
    NPC witnessed_observer;
    witnessed_observer.entity_id = "observing-npc";
    witnessed_observer.district_id = "observed-district";
    witnessed_information_state.npcs = {witnessed_actor, witnessed_observer};
    SimulationWorld witnessed_information_world(witnessed_information_state, 2.0, 2025U);
    assert(witnessed_information_world.record_witnessed_action(
        "observed-actor", ActionTag::CrimeTheft, Description{},
        {"observing-npc"}) == 1U);
    assert(witnessed_information_world.information_ledger().size() == 1U);
    const InformationClaim* witness_claim = witnessed_information_world.information_ledger().find(
        "observation:event-1:observing-npc");
    assert(witness_claim != nullptr);
    assert(witness_claim->subject_key == "observed-actor");
    assert(witness_claim->recipient_entity_id == "observing-npc");
    assert(witness_claim->kind == InformationKind::Observation);

    NPC conversation_listener;
    conversation_listener.entity_id = "listening-npc";
    conversation_listener.district_id = "observed-district";
    witnessed_information_world.state().npcs.push_back(conversation_listener);
    const Conversation first_conversation = witnessed_information_world.talk(
        "listening-npc", "observing-npc");
    assert(first_conversation.transferred.size() == 1U);
    assert(witnessed_information_world.information_ledger().size() == 2U);
    const InformationClaim* first_relay = witnessed_information_world.information_ledger().find(
        "relay:observation:event-1:observing-npc:listening-npc:2000");
    assert(first_relay != nullptr);
    assert(first_relay->root_evidence_id == witness_claim->root_evidence_id);
    assert(first_relay->hop_count == 1U);

    NPC next_listener;
    next_listener.entity_id = "third-npc";
    next_listener.district_id = "observed-district";
    witnessed_information_world.state().npcs.push_back(next_listener);
    const Conversation second_conversation = witnessed_information_world.talk(
        "third-npc", "listening-npc");
    assert(second_conversation.transferred.size() == 1U);
    assert(witnessed_information_world.information_ledger().size() == 3U);
    const InformationClaim* second_relay = witnessed_information_world.information_ledger().find(
        "relay:relay:observation:event-1:observing-npc:listening-npc:2000:third-npc:2000");
    assert(second_relay != nullptr);
    assert(second_relay->root_evidence_id == witness_claim->root_evidence_id);
    assert(second_relay->hop_count == 2U);
    assert(witnessed_information_world.information_ledger().independent_evidence_count(
        "observed-actor", std::to_string(static_cast<unsigned int>(ActionTag::CrimeTheft))) == 1U);

    const auto find_observed_theft_belief = [](const NPC& npc) -> const NPCBelief& {
        const auto found = std::find_if(npc.beliefs.begin(), npc.beliefs.end(),
            [](const NPCBelief& belief) {
                return belief.target_entity_id == "observed-actor"
                    && belief.action_tag == ActionTag::CrimeTheft
                    && belief.timestamp_hour == 2.0;
            });
        assert(found != npc.beliefs.end());
        return *found;
    };
    const NPCBelief before_same_lineage_return = find_observed_theft_belief(
        witnessed_information_world.state().npcs[2]);
    const double confidence_before_same_lineage_return = before_same_lineage_return.confidence;
    const std::uint32_t corroborations_before_same_lineage_return =
        before_same_lineage_return.corroborations;
    const double relationship_before_same_lineage_return =
        witnessed_information_world.state().npcs[2].relationships["observed-actor"];
    (void)witnessed_information_world.talk("listening-npc", "third-npc");
    const NPCBelief& after_same_lineage_return = find_observed_theft_belief(
        witnessed_information_world.state().npcs[2]);
    assert(after_same_lineage_return.confidence == confidence_before_same_lineage_return);
    assert(after_same_lineage_return.corroborations == corroborations_before_same_lineage_return);
    assert(witnessed_information_world.state().npcs[2].relationships["observed-actor"]
        == relationship_before_same_lineage_return);
    assert(witnessed_information_world.information_ledger().independent_evidence_count(
        "observed-actor", std::to_string(static_cast<unsigned int>(ActionTag::CrimeTheft))) == 1U);

    // Independent witnesses can revise an existing second-hand belief,
    // while skepticism changes how strongly the listener accepts each account.
    const auto belief_revision_result = [](double skepticism) {
        WorldState revision_state;
        NPC revision_actor;
        revision_actor.entity_id = "revision-actor";
        revision_actor.district_id = "revision-district";
        NPC first_witness;
        first_witness.entity_id = "revision-witness-a";
        first_witness.district_id = "revision-district";
        NPC second_witness;
        second_witness.entity_id = "revision-witness-b";
        second_witness.district_id = "revision-district";
        NPC revision_listener;
        revision_listener.entity_id = "revision-listener";
        revision_listener.district_id = "revision-district";
        revision_listener.skepticism = skepticism;
        revision_state.npcs = {revision_actor, first_witness, second_witness, revision_listener};
        SimulationWorld revision_world(revision_state, 4.0, 2027U);

        assert(revision_world.record_witnessed_action(
            "revision-actor", ActionTag::CrimeTheft, Description{},
            {"revision-witness-a"}) == 1U);
        (void)revision_world.talk("revision-listener", "revision-witness-a");
        const auto find_revision_belief = [&revision_world]() -> const NPCBelief& {
            const auto found = std::find_if(
                revision_world.state().npcs[3].beliefs.begin(),
                revision_world.state().npcs[3].beliefs.end(),
                [](const NPCBelief& belief) {
                    return belief.target_entity_id == "revision-actor"
                        && belief.action_tag == ActionTag::CrimeTheft
                        && belief.timestamp_hour == 4.0;
                });
            assert(found != revision_world.state().npcs[3].beliefs.end());
            return *found;
        };
        const double first_confidence = find_revision_belief().confidence;
        const std::uint32_t first_corroborations = find_revision_belief().corroborations;

        // A second event at the same simulation hour has a distinct root ID;
        // it is independent evidence, not another relay of the first event.
        assert(revision_world.record_witnessed_action(
            "revision-actor", ActionTag::CrimeTheft, Description{},
            {"revision-witness-b"}) == 1U);
        (void)revision_world.talk("revision-listener", "revision-witness-b");
        const double revised_confidence = find_revision_belief().confidence;
        const std::uint32_t revised_corroborations = find_revision_belief().corroborations;
        const std::size_t independent_roots =
            revision_world.information_ledger().independent_evidence_count(
                "revision-actor",
                std::to_string(static_cast<unsigned int>(ActionTag::CrimeTheft)));
        assert(revision_world.state().npcs[3].belief_revision_history.size() == 1U);
        assert(revision_world.state().npcs[3].belief_revision_history.front().reason
            == BeliefRevisionReason::IndependentEvidence);
        return std::tuple<double, double, std::uint32_t, std::uint32_t, std::size_t>{
            first_confidence, revised_confidence, first_corroborations,
            revised_corroborations, independent_roots};
    };
    const auto open_revision = belief_revision_result(0.0);
    const auto skeptical_revision = belief_revision_result(1.0);
    assert(std::get<1>(open_revision) > std::get<0>(open_revision));
    assert(std::get<3>(open_revision) == std::get<2>(open_revision) + 1U);
    assert(std::get<4>(open_revision) == 2U);
    assert(std::get<1>(skeptical_revision) > std::get<0>(skeptical_revision));
    assert(std::get<1>(open_revision) > std::get<1>(skeptical_revision));

    // Information claim lineage is part of the saved world and remains stable
    // across save/resume, including deterministic serialized bytes.
    WorldState information_state;
    NPC revision_history_npc;
    revision_history_npc.entity_id = "revision-history-npc";
    revision_history_npc.belief_revision_history.push_back(BeliefRevision{
        "history-target", ActionTag::CrimeTheft, 3.0, 0.4, 0.7,
        BeliefRevisionReason::IndependentEvidence, "history-source", 4.0,
        0.8, 1.1, 0.95, 0.8, 0.9});
    revision_history_npc.belief_revision_history.back().evidence_claim_ids = {
        "claim-alpha", "claim-beta"};
    revision_history_npc.belief_revision_history.back().evidence_root_ids = {
        "root-alpha", "root-beta"};
    information_state.npcs.push_back(revision_history_npc);
    SimulationWorld information_world(information_state, 0.0, 2026U);

    // Belief history queries are read-only, target-filterable, and chronological.
    WorldState history_query_state;
    NPC history_query_npc;
    history_query_npc.entity_id = "history-query-npc";
    history_query_npc.belief_revision_history = {
        BeliefRevision{"target-a", ActionTag::CrimeTheft, 8.0, 0.4, 0.2,
            BeliefRevisionReason::Contradiction, "source-c", 9.0},
        BeliefRevision{"target-b", ActionTag::SocialAid, 2.0, 0.1, 0.3,
            BeliefRevisionReason::IndependentEvidence, "source-a", 3.0},
        BeliefRevision{"target-a", ActionTag::CrimeTheft, 4.0, 0.4, 0.6,
            BeliefRevisionReason::IndependentEvidence, "source-b", 5.0}
    };
    history_query_state.npcs.push_back(history_query_npc);
    const SimulationWorld history_query_world(history_query_state, 0.0, 2027U);
    const auto all_history = history_query_world.belief_history_for("history-query-npc");
    assert(all_history.size() == 3U);
    assert(all_history[0].recorded_hour == 3.0);
    assert(all_history[1].recorded_hour == 5.0);
    assert(all_history[2].recorded_hour == 9.0);
    const auto target_history =
        history_query_world.belief_history_for("history-query-npc", "target-a");
    assert(target_history.size() == 2U);
    assert(target_history[0].event_timestamp_hour == 4.0);
    assert(target_history[1].event_timestamp_hour == 8.0);
    assert(history_query_world.belief_history_for("missing-npc").empty());
    const auto explanations =
        history_query_world.belief_explanations_for("history-query-npc", "target-a");
    assert(explanations.size() == 2U);
    assert(std::abs(explanations[0].confidence_delta - 0.2) < 1e-12);
    assert(std::abs(explanations[1].confidence_delta - (-0.2)) < 1e-12);
    assert(explanations[0].revision.reason == BeliefRevisionReason::IndependentEvidence);
    assert(explanations[1].revision.reason == BeliefRevisionReason::Contradiction);
    assert(history_query_world.belief_explanations_for("missing-npc").empty());

    // Competing interpretations of one event are returned together, not collapsed.
    WorldState competing_accounts_state;
    NPC competing_accounts_npc;
    competing_accounts_npc.entity_id = "competing-accounts-npc";
    competing_accounts_npc.beliefs = {
        NPCBelief{"target", ActionTag::CrimeTheft, 12.0, 0.35, "rumour-source", false, 0U, 1U},
        NPCBelief{"target", ActionTag::SocialAid, 12.0, 0.8, "friend-source", false, 1U, 0U},
        NPCBelief{"target", ActionTag::CrimeTheft, 13.0, 0.7, "later-source", false, 0U, 0U}
    };
    competing_accounts_state.npcs.push_back(competing_accounts_npc);
    const SimulationWorld competing_accounts_world(competing_accounts_state, 0.0, 2028U);
    const auto same_event_accounts =
        competing_accounts_world.beliefs_about_event("competing-accounts-npc", "target", 12.0);
    assert(same_event_accounts.size() == 2U);
    assert(same_event_accounts[0].action_tag == ActionTag::CrimeTheft);
    assert(same_event_accounts[1].action_tag == ActionTag::SocialAid);
    assert(same_event_accounts[0].source_entity_id == "rumour-source");
    assert(same_event_accounts[1].source_entity_id == "friend-source");
    assert(competing_accounts_world.beliefs_about_event("missing-npc", "target", 12.0).empty());
    assert(competing_accounts_world.beliefs_about_event("competing-accounts-npc", "", 12.0).empty());
    assert(competing_accounts_world.beliefs_about_event(
        "competing-accounts-npc", "target", std::numeric_limits<double>::quiet_NaN()).empty());
    // Account explanations join only revisions for the same interpretation and
    // event timestamp; accounts without history remain visible.
    competing_accounts_npc.belief_revision_history = {
        BeliefRevision{"target", ActionTag::CrimeTheft, 12.0, 0.2, 0.35,
            BeliefRevisionReason::IndependentEvidence, "rumour-source", 14.0},
        BeliefRevision{"target", ActionTag::CrimeTheft, 12.0, 0.35, 0.25,
            BeliefRevisionReason::Contradiction, "other-source", 15.0},
        BeliefRevision{"target", ActionTag::SocialAid, 12.0, 0.5, 0.8,
            BeliefRevisionReason::IndependentEvidence, "friend-source", 16.0},
        BeliefRevision{"target", ActionTag::CrimeTheft, 13.0, 0.4, 0.7,
            BeliefRevisionReason::IndependentEvidence, "later-source", 17.0}
    };
    competing_accounts_state.npcs.clear();
    competing_accounts_state.npcs.push_back(competing_accounts_npc);
    const SimulationWorld explained_accounts_world(competing_accounts_state, 0.0, 2029U);
    const auto account_explanations =
        explained_accounts_world.belief_account_explanations_for(
            "competing-accounts-npc", "target", 12.0);
    assert(account_explanations.size() == 2U);
    assert(account_explanations[0].current_belief.action_tag == ActionTag::CrimeTheft);
    assert(account_explanations[0].revisions.size() == 2U);
    assert(account_explanations[0].revisions[0].revision.recorded_hour == 14.0);
    assert(account_explanations[0].revisions[1].revision.recorded_hour == 15.0);
    assert(std::abs(account_explanations[0].revisions[0].confidence_delta - 0.15) < 1e-12);
    assert(std::abs(account_explanations[0].revisions[1].confidence_delta - (-0.1)) < 1e-12);
    assert(account_explanations[1].current_belief.action_tag == ActionTag::SocialAid);
    assert(account_explanations[1].revisions.size() == 1U);
    assert(account_explanations[1].revisions[0].revision.recorded_hour == 16.0);
    assert(explained_accounts_world.belief_account_explanations_for(
        "missing-npc", "target", 12.0).empty());
    assert(explained_accounts_world.belief_account_explanations_for(
        "competing-accounts-npc", "target", std::numeric_limits<double>::infinity()).empty());

    // The joined investigation view keeps received claims, conflicting current
    // beliefs, and chronological confidence changes as distinct information.
    WorldState investigation_view_state;
    NPC investigating_npc;
    investigating_npc.entity_id = "investigating-npc";
    investigating_npc.beliefs = {
        NPCBelief{"bridge-7", ActionTag::CrimeTheft, 6.0, 0.35, "witness-a", true, 1U, 1U},
        NPCBelief{"bridge-7", ActionTag::SocialAid, 6.0, 0.65, "witness-b", false, 1U, 0U}
    };
    investigating_npc.belief_revision_history = {
        BeliefRevision{"bridge-7", ActionTag::CrimeTheft, 6.0, 0.5, 0.35,
            BeliefRevisionReason::Contradiction, "witness-b", 8.0,
            0.7, 1.1, 0.9, 1.2, 0.8}
    };
    investigating_npc.belief_revision_history.back().evidence_claim_ids = {
        "view-claim-a-relay", "missing-claim"};
    investigating_npc.belief_revision_history.back().evidence_root_ids = {
        "inspection-a", "missing-root"};
    investigation_view_state.npcs.push_back(investigating_npc);
    NPC second_investigator;
    second_investigator.entity_id = "second-investigator";
    second_investigator.beliefs = {
        NPCBelief{"bridge-7", ActionTag::SocialAid, 6.0, 0.9, "witness-c", true, 2U, 0U}
    };
    investigation_view_state.npcs.push_back(second_investigator);
    SimulationWorld investigation_view_world(investigation_view_state, 0.0, 2030U);
    InformationClaim view_claim_a;
    view_claim_a.claim_id = "view-claim-a";
    view_claim_a.subject_key = "bridge-7";
    view_claim_a.proposition_key = "bridge-safe";
    view_claim_a.root_evidence_id = "inspection-a";
    view_claim_a.source_entity_id = "inspector-origin";
    view_claim_a.recipient_entity_id = "inspector-a";
    view_claim_a.confidence = 0.8;
    assert(investigation_view_world.information_ledger().record(view_claim_a).accepted);
    assert(investigation_view_world.information_ledger().relay(
        "view-claim-a", "view-claim-a-relay", "inspector-a",
        "investigating-npc", 1, 0.9).accepted);
    InformationClaim view_claim_b = view_claim_a;
    view_claim_b.claim_id = "view-claim-b";
    view_claim_b.proposition_key = "bridge-unsafe";
    view_claim_b.root_evidence_id = "inspection-b";
    view_claim_b.recipient_entity_id = "investigating-npc";
    view_claim_b.confidence = 0.7;
    assert(investigation_view_world.information_ledger().record(view_claim_b).accepted);
    InformationClaim private_claim = view_claim_a;
    private_claim.claim_id = "view-claim-private";
    private_claim.subject_key = "different-subject";
    private_claim.recipient_entity_id = "another-npc";
    assert(investigation_view_world.information_ledger().record(private_claim).accepted);
    InformationClaim second_npc_claim = view_claim_b;
    second_npc_claim.claim_id = "view-claim-second-npc";
    second_npc_claim.recipient_entity_id = "second-investigator";
    second_npc_claim.root_evidence_id = "inspection-c";
    assert(investigation_view_world.information_ledger().record(second_npc_claim).accepted);

    const NPCInvestigationView investigation_view =
        investigation_view_world.investigation_view_for("investigating-npc");
    assert(investigation_view.npc_id == "investigating-npc");
    assert(investigation_view.received_information.size() == 2U);
    assert(investigation_view.current_beliefs.size() == 2U);
    assert(investigation_view.current_beliefs[0].action_tag == ActionTag::CrimeTheft);
    assert(investigation_view.current_beliefs[1].action_tag == ActionTag::SocialAid);
    assert(investigation_view.belief_history.size() == 1U);
    assert(investigation_view.belief_history[0].revision.source_reliability == 0.7);
    assert(investigation_view.belief_history[0].revision.loyalty_factor == 1.1);
    assert(investigation_view.belief_history[0].revision.compassion_factor == 0.9);
    assert(investigation_view.belief_history[0].revision.skepticism_factor == 1.2);
    assert(investigation_view.belief_history[0].revision.evidence_factor == 0.8);
    assert(investigation_view.belief_history[0].revision.evidence_root_ids.size() == 2U);
    assert(investigation_view.belief_history[0].evidence_claims.size() == 2U);
    assert(investigation_view.belief_history[0].evidence_claims[0].requested_claim_id == "view-claim-a-relay");
    assert(investigation_view.belief_history[0].evidence_claims[0].resolved);
    assert(investigation_view.belief_history[0].evidence_claims[0].claim.root_evidence_id == "inspection-a");
    assert(investigation_view.belief_history[0].evidence_claims[0].lineage.size() == 2U);
    assert(investigation_view.belief_history[0].evidence_claims[0].lineage.front().claim_id == "view-claim-a");
    assert(investigation_view.belief_history[0].evidence_claims[0].lineage.back().claim_id == "view-claim-a-relay");
    assert(investigation_view.belief_history[0].evidence_claims[1].requested_claim_id == "missing-claim");
    assert(!investigation_view.belief_history[0].evidence_claims[1].resolved);
    assert(std::abs(investigation_view.belief_history[0].confidence_delta - (-0.15)) < 1e-12);
    assert(investigation_view.belief_accounts.size() == 2U);
    assert(investigation_view.belief_accounts[0].current_belief.action_tag == ActionTag::CrimeTheft);
    assert(investigation_view.belief_accounts[0].revisions.size() == 1U);
    assert(investigation_view.belief_accounts[1].current_belief.action_tag == ActionTag::SocialAid);
    assert(investigation_view.belief_accounts[1].revisions.empty());
    const NPCInvestigationView filtered_investigation =
        investigation_view_world.investigation_view_for("investigating-npc", "bridge-7");
    assert(filtered_investigation.received_information.size() == 2U);
    assert(filtered_investigation.current_beliefs.size() == 2U);
    assert(investigation_view_world.investigation_view_for("missing-npc").received_information.empty());
    assert(investigation_view_world.investigation_view_for("missing-npc").current_beliefs.empty());

    // The same subject can have different recipient-local evidence and
    // interpretations; the view exposes the difference without adjudicating it.
    const NPCInvestigationView second_view =
        investigation_view_world.investigation_view_for("second-investigator");
    assert(second_view.received_information.size() == 1U);
    assert(second_view.received_information[0].proposition_key == "bridge-unsafe");
    assert(second_view.current_beliefs.size() == 1U);
    assert(second_view.current_beliefs[0].action_tag == ActionTag::SocialAid);
    assert(second_view.current_beliefs[0].confidence == 0.9);
    InformationClaim observed_claim;
    observed_claim.claim_id = "claim-observed";
    observed_claim.subject_key = "bridge-7";
    observed_claim.proposition_key = "bridge-unsafe";
    observed_claim.root_evidence_id = "inspection-42";
    observed_claim.source_entity_id = "inspector";
    observed_claim.recipient_entity_id = "resident-a";
    observed_claim.created_tick = 3;
    observed_claim.confidence = 0.95;
    observed_claim.kind = InformationKind::Observation;
    assert(information_world.information_ledger().record(observed_claim).accepted);
    assert(information_world.information_ledger().relay(
        "claim-observed", "claim-relayed", "resident-a", "resident-b", 4, 0.8).accepted);
    std::stringstream information_snapshot(std::ios::in | std::ios::out | std::ios::binary);
    save_world(information_world, information_snapshot);
    information_snapshot.seekg(0);
    SimulationWorld information_restored = load_world(information_snapshot);
    assert(information_restored.state().npcs.size() == 1U);
    assert(information_restored.state().npcs.front().belief_revision_history.size() == 1U);
    const BeliefRevision& restored_revision =
        information_restored.state().npcs.front().belief_revision_history.front();
    assert(restored_revision.reason == BeliefRevisionReason::IndependentEvidence);
    assert(restored_revision.previous_confidence == 0.4);
    assert(restored_revision.revised_confidence == 0.7);
    assert(restored_revision.source_entity_id == "history-source");
    assert(restored_revision.source_reliability == 0.8);
    assert(restored_revision.loyalty_factor == 1.1);
    assert(restored_revision.compassion_factor == 0.95);
    assert(restored_revision.skepticism_factor == 0.8);
    assert(restored_revision.evidence_factor == 0.9);
    assert(restored_revision.evidence_claim_ids.size() == 2U);
    assert(restored_revision.evidence_claim_ids[0] == "claim-alpha");
    assert(restored_revision.evidence_claim_ids[1] == "claim-beta");
    assert(restored_revision.evidence_root_ids.size() == 2U);
    assert(restored_revision.evidence_root_ids[0] == "root-alpha");
    assert(restored_revision.evidence_root_ids[1] == "root-beta");
    assert(restored_revision.source_reliability == 0.8);
    assert(restored_revision.loyalty_factor == 1.1);
    assert(restored_revision.compassion_factor == 0.95);
    assert(restored_revision.skepticism_factor == 0.8);
    assert(restored_revision.evidence_factor == 0.9);
    assert(information_restored.information_ledger().size() == 2U);
    assert(information_restored.information_ledger().find("claim-relayed") != nullptr);
    assert(information_restored.information_ledger().find("claim-relayed")->hop_count == 1U);
    assert(information_restored.information_ledger().independent_evidence_count(
        "bridge-7", "bridge-unsafe") == 1U);
    std::stringstream information_bytes_a(std::ios::in | std::ios::out | std::ios::binary);
    std::stringstream information_bytes_b(std::ios::in | std::ios::out | std::ios::binary);
    save_world(information_world, information_bytes_a);
    save_world(information_restored, information_bytes_b);
    assert(information_bytes_a.str() == information_bytes_b.str());

    return 0;
}

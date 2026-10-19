#include "simreality/CoreTypes.h"
#include "simreality/Decay.h"
#include "simreality/Districts.h"
#include "simreality/Ecosystem.h"
#include "simreality/Fixers.h"
#include "simreality/Gossip.h"
#include "simreality/Justice.h"
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
#include <sstream>
#include <stdexcept>
#include <utility>

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
    NPC speaker_npc;
    speaker_npc.entity_id = "speaker";
    speaker_npc.district_id = "D1";
    speaker_npc.home_id = "home-speaker";
    speaker_npc.job_id = "job-shop";
    speaker_npc.hourly_wage = 12.5;
    speaker_npc.daily_rent = 4.0;
    speaker_npc.money = 50.0;
    speaker_npc.relationships["listener"] = 0.75;
    speaker_npc.goals = {"keep_job", "save_for_home"};
    speaker_npc.schedule = {{DailyActivity::Work, 9, 17}, {DailyActivity::Sleep, 22, 6}};
    NPC listener_npc;
    listener_npc.entity_id = "listener";
    listener_npc.district_id = "D1";
    NPC player_npc;
    player_npc.entity_id = "player";
    player_npc.district_id = "D1";
    initial_world.npcs = {speaker_npc, listener_npc, player_npc};
    SimulationWorld world(std::move(initial_world), 0.0, 99U);
    Description scene_description;
    scene_description.height_m = 1.82;
    scene_description.jacket_colour_weights = {{"black", 0.8}};
    assert(world.record_witnessed_action(
        "player", ActionTag::CrimeTheft, scene_description,
        {"speaker", "listener", "speaker"}, "listener") == 2);
    assert(world.state().npcs[0].personal_stress > 0.0);
    assert(world.state().npcs[1].personal_stress > world.state().npcs[0].personal_stress);
    const Conversation world_conversation = world.talk("listener", "speaker");
    assert(world_conversation.transferred.size() == 1);
    assert(world.state().npcs[1].memories.size() == 1);
    CriminalFile world_file = world.build_criminal_file("player");
    assert(world_file.charges.size() == 1);
    assert(world_file.charges[0].evidence == EvidenceKind::Corroborated);
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
    assert(world.fixer_networks()[0].members[0].standing ==
        deterministic_peer.fixer_networks()[0].members[0].standing);
    assert(world.total_hours() == 24.0);
    assert(world.day_index() == 1);
    assert(world_report.memories_swept == 48);
    assert(world_report.daily_results.size() == 1);
    assert(world_report.daily_results[0].residents.size() == 3);

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
    assert(restored.state().npcs[0].money == world.state().npcs[0].money);
    assert(restored.state().districts[0].shop_stock == world.state().districts[0].shop_stock);
    assert(restored.state().districts[0].cash_circulation == world.state().districts[0].cash_circulation);
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

    bool rejected_bad_snapshot = false;
    try {
        std::stringstream invalid_snapshot("not-a-snapshot");
        (void)load_world(invalid_snapshot);
    } catch (const std::runtime_error&) {
        rejected_bad_snapshot = true;
    }
    assert(rejected_bad_snapshot);

    return 0;
}

#include "simreality/TrafficRecovery.h"
#include "simreality/RoutePlanning.h"
#include "simreality/WorldPersistence.h"

#include <cassert>
#include <stdexcept>
#include <sstream>
#include <vector>

using namespace simreality;

int main() {
    LaneTrafficCoordinator lanes(3U);
    lanes.configure_lane("L1", 2U);
    IntersectionTrafficCoordinator intersections(3U);
    intersections.configure_movement({"J1", "M1", {"Z1"}});
    lanes.advance_tick(10U);
    intersections.advance_tick(10U);
    assert(lanes.resolve({{"L1", "npc-a", 0}}).granted_entity_ids.size() == 1U);
    assert(intersections.resolve({{"J1", "M1", "npc-a", 0}}).granted_entity_ids.size() == 1U);

    JourneyReservationManager journey;
    journey.track({"npc-a", "L1", "J1", "M1"});
    const auto renewed = journey.advance_and_renew(11U, lanes, intersections);
    assert(renewed.lanes.granted_entity_ids == std::vector<std::string>{"npc-a"});
    assert(renewed.intersections.granted_entity_ids == std::vector<std::string>{"npc-a"});
    assert(lanes.has_reservation("L1", "npc-a"));
    assert(intersections.has_reservation("J1", "M1", "npc-a"));

    // An unknown intersection movement fails after lane renewal has run.
    // The manager must roll back both coordinators, including lane expiry.
    journey.track({"npc-b", "L1", "missing-junction", "missing-movement"});
    const auto lane_before_failure = lanes.snapshot();
    const auto intersection_before_failure = intersections.snapshot();
    bool renewal_failed = false;
    try {
        (void)journey.advance_and_renew(12U, lanes, intersections);
    } catch (const std::out_of_range&) {
        renewal_failed = true;
    }
    assert(renewal_failed);
    assert(lanes.current_tick() == lane_before_failure.current_tick);
    assert(intersections.current_tick() == intersection_before_failure.current_tick);
    assert(lanes.reservations("L1").front().expires_at_tick
        == lane_before_failure.reservations.front().expires_at_tick);
    assert(intersections.reservations("J1").front().expires_at_tick
        == intersection_before_failure.reservations.front().expires_at_tick);
    assert(journey.forget_after_clearance("npc-b"));

    assert(journey.forget_after_clearance("npc-a"));
    // Forgetting tracking is deliberately not a release operation.
    assert(lanes.has_reservation("L1", "npc-a"));
    assert(intersections.has_reservation("J1", "M1", "npc-a"));
    journey.track({"npc-a", "L1", "J1", "M1"});

    TrafficDeadlockDetector detector;
    const auto cycles = detector.detect({
        {"a", "b"}, {"b", "c"}, {"c", "a"}, {"d", "e"}});
    assert(cycles.size() == 1U);
    assert((cycles.front() == std::vector<std::string>{"a", "b", "c"}));
    assert(detector.detect({{"a", "b"}, {"b", "c"}}).empty());
    const auto stable = detector.detect({
        {"c", "a"}, {"b", "c"}, {"a", "b"}, {"e", "d"}, {"d", "e"}});
    assert(stable.size() == 2U);
    assert((stable[0] == std::vector<std::string>{"a", "b", "c"}));
    assert((stable[1] == std::vector<std::string>{"d", "e"}));

    bool duplicate_rejected = false;
    try { (void)detector.detect({{"a", "b"}, {"a", "b"}}); }
    catch (const std::invalid_argument&) { duplicate_rejected = true; }
    assert(duplicate_rejected);

    const auto proposals = detector.propose_resolutions({
        {"a", "b", BlockedResourceKind::Lane, "lane-a"},
        {"b", "c", BlockedResourceKind::Intersection, "junction-1"},
        {"c", "a", BlockedResourceKind::Lane, "lane-c"}},
        {{"b", {{{"detour-b", "b", 0}}, {{"junction-2", "detour", "b", 0}}}}});
    assert(proposals.size() == 1U);
    assert(proposals.front().yielding_entity_id == "b");
    assert(proposals.front().blocking_resources.size() == 3U);
    assert(proposals.front().replacement_lane_requests.size() == 1U);
    assert(proposals.front().replacement_intersection_requests.size() == 1U);

    RouteProgressMonitor progress_monitor(3U);
    (void)progress_monitor.observe("npc-a", 10U, 0.0);
    (void)progress_monitor.observe("npc-a", 11U, 0.0);
    TrafficRecoveryCheckpoint checkpoint;
    checkpoint.lanes = lanes.snapshot();
    checkpoint.intersections = intersections.snapshot();
    checkpoint.journey_occupancy = journey.snapshot();
    checkpoint.progress_stall_threshold = progress_monitor.stalled_tick_threshold();
    checkpoint.route_progress = progress_monitor.snapshot();
    checkpoint.pending_proposals = proposals;
    checkpoint.pending_wait_edges = {
        {"npc-a", "npc-b", BlockedResourceKind::Lane, "L1"},
        {"npc-b", "npc-a", BlockedResourceKind::Intersection, "J1"}};
    std::stringstream checkpoint_bytes(std::ios::in | std::ios::out | std::ios::binary);
    save_traffic_recovery_checkpoint(checkpoint, checkpoint_bytes);
    const std::string durable_bytes = checkpoint_bytes.str();

    auto inconsistent_checkpoint = checkpoint;
    inconsistent_checkpoint.lanes.reservations.clear();
    std::stringstream rejected_checkpoint(std::ios::in | std::ios::out | std::ios::binary);
    bool inconsistent_rejected = false;
    try {
        save_traffic_recovery_checkpoint(inconsistent_checkpoint, rejected_checkpoint);
    } catch (const std::invalid_argument&) {
        inconsistent_rejected = true;
    }
    assert(inconsistent_rejected);
    assert(rejected_checkpoint.str().empty());

    // Encoding limits are also checked before the caller's stream is touched.
    auto oversized_checkpoint = checkpoint;
    oversized_checkpoint.lanes.capacities.emplace(
        std::string(16U * 1024U * 1024U + 1U, 'x'), 1U);
    std::stringstream oversized_bytes(std::ios::in | std::ios::out | std::ios::binary);
    bool oversized_rejected = false;
    try {
        save_traffic_recovery_checkpoint(oversized_checkpoint, oversized_bytes);
    } catch (const std::length_error&) {
        oversized_rejected = true;
    }
    assert(oversized_rejected);
    assert(oversized_bytes.str().empty());

    auto malformed_proposal_checkpoint = checkpoint;
    malformed_proposal_checkpoint.pending_proposals.front().participants = {"", "b", "c"};
    std::stringstream malformed_proposal_bytes(std::ios::in | std::ios::out | std::ios::binary);
    bool malformed_proposal_rejected = false;
    try {
        save_traffic_recovery_checkpoint(malformed_proposal_checkpoint, malformed_proposal_bytes);
    } catch (const std::invalid_argument&) {
        malformed_proposal_rejected = true;
    }
    assert(malformed_proposal_rejected);
    assert(malformed_proposal_bytes.str().empty());

    std::stringstream trailing_data(durable_bytes + "x",
        std::ios::in | std::ios::binary);
    bool trailing_data_rejected = false;
    try {
        (void)load_traffic_recovery_checkpoint(trailing_data);
    } catch (const std::runtime_error&) {
        trailing_data_rejected = true;
    }
    assert(trailing_data_rejected);

    checkpoint_bytes.seekg(0);
    const auto restored_checkpoint = load_traffic_recovery_checkpoint(checkpoint_bytes);
    assert(restored_checkpoint.lanes.reservations.size() == checkpoint.lanes.reservations.size());
    assert(restored_checkpoint.intersections.reservations.size() == checkpoint.intersections.reservations.size());
    assert(restored_checkpoint.journey_occupancy.size() == 1U);
    assert(restored_checkpoint.route_progress.front().stalled_ticks == 1U);
    assert(restored_checkpoint.pending_wait_edges.size() == 2U);
    assert(restored_checkpoint.pending_proposals.size() == 1U);
    assert(restored_checkpoint.pending_proposals.front().yielding_entity_id == "b");

    LaneTrafficCoordinator restored_lanes;
    restored_lanes.restore(restored_checkpoint.lanes);
    IntersectionTrafficCoordinator restored_intersections;
    restored_intersections.restore(restored_checkpoint.intersections);
    JourneyReservationManager restored_journey;
    restored_journey.restore(restored_checkpoint.journey_occupancy);
    RouteProgressMonitor restored_progress(restored_checkpoint.progress_stall_threshold);
    restored_progress.restore(restored_checkpoint.route_progress);
    const auto resumed = restored_journey.advance_and_renew(
        12U, restored_lanes, restored_intersections);
    assert(resumed.lanes.granted_entity_ids == std::vector<std::string>{"npc-a"});
    assert(resumed.intersections.granted_entity_ids == std::vector<std::string>{"npc-a"});
    assert(restored_progress.observe("npc-a", 12U, 0.0).stalled_ticks == 2U);
    std::stringstream resaved(std::ios::in | std::ios::out | std::ios::binary);
    save_traffic_recovery_checkpoint(restored_checkpoint, resaved);
    assert(resaved.str() == durable_bytes);

    bool malformed_rejected = false;
    try { journey.track({"npc-b", "L2", "J2", {}}); }
    catch (const std::invalid_argument&) { malformed_rejected = true; }
    assert(malformed_rejected);
    return 0;
}

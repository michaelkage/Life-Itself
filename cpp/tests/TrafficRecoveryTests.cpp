#include "simreality/TrafficRecovery.h"

#include <cassert>
#include <stdexcept>
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

    assert(journey.forget_after_clearance("npc-a"));
    // Forgetting tracking is deliberately not a release operation.
    assert(lanes.has_reservation("L1", "npc-a"));
    assert(intersections.has_reservation("J1", "M1", "npc-a"));

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

    bool malformed_rejected = false;
    try { journey.track({"npc-b", "L2", "J2", {}}); }
    catch (const std::invalid_argument&) { malformed_rejected = true; }
    assert(malformed_rejected);
    return 0;
}

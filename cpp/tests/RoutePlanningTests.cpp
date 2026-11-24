#include "simreality/RoutePlanning.h"

#include <cassert>
#include <stdexcept>
#include <string>
#include <vector>

using namespace simreality;

int main() {
    TrafficRoutePlanner planner;
    planner.upsert_edge({"A", "B", "J1", "through", 1.0, 2.0, 0.0});
    planner.upsert_edge({"B", "D", "J2", "left", 1.0, 2.0, 0.0});
    planner.upsert_edge({"A", "C", "J3", "through", 2.0, 0.0, 0.0});
    planner.upsert_edge({"C", "D", "J4", "right", 2.0, 0.0, 0.0});

    const auto shortest = planner.plan("A", "D");
    assert(shortest.steps.size() == 3U);
    assert(shortest.steps[1].lane_id == "B");
    assert(shortest.total_cost == 2.0);

    const auto uncongested_alternate = planner.plan("A", "D", {{"B", 2U}});
    assert(uncongested_alternate.steps[1].lane_id == "C");
    assert(uncongested_alternate.total_cost == 4.0);

    TrafficRoutePlanner ties;
    ties.upsert_edge({"S", "Z", {}, {}, 1.0, 0.0, 0.0});
    ties.upsert_edge({"Z", "T", {}, {}, 1.0, 0.0, 0.0});
    ties.upsert_edge({"S", "A", {}, {}, 1.0, 0.0, 0.0});
    ties.upsert_edge({"A", "T", {}, {}, 1.0, 0.0, 0.0});
    assert(ties.plan("S", "T").steps[1].lane_id == "A");

    const auto intents = planner.reservation_lookahead(shortest, 0U, "npc-1", 5, 2U);
    assert(intents.lane_requests.size() == 2U);
    assert(intents.intersection_requests.size() == 2U);
    assert(intents.lane_requests[0].lane_id == "B");
    assert(intents.intersection_requests[0].movement_id == "through");

    RoutePlan stale_route = shortest;
    stale_route.steps[1].entry_movement_id = "wrong-movement";
    bool stale_rejected = false;
    try { (void)planner.reservation_lookahead(stale_route, 0U, "npc-1", 5, 1U); }
    catch (const std::invalid_argument&) { stale_rejected = true; }
    assert(stale_rejected);

    bool unreachable = false;
    try { (void)planner.plan("D", "A"); }
    catch (const std::runtime_error&) { unreachable = true; }
    assert(unreachable);

    bool invalid_edge = false;
    try { planner.upsert_edge({"X", "Y", "junction", {}, 1.0, 0.0, 0.0}); }
    catch (const std::invalid_argument&) { invalid_edge = true; }
    assert(invalid_edge);

    RouteProgressMonitor monitor(3U);
    assert(monitor.observe("npc-1", 10U, 0.0).action == RouteRecoveryAction::None);
    assert(monitor.observe("npc-1", 11U, 0.0).stalled_ticks == 1U);
    assert(monitor.observe("npc-1", 12U, 0.0).stalled_ticks == 2U);
    assert(monitor.observe("npc-1", 13U, 0.0).action == RouteRecoveryAction::ReplanRequested);
    assert(monitor.observe("npc-1", 14U, 1.0).stalled_ticks == 0U);
    bool stale_tick = false;
    try { (void)monitor.observe("npc-1", 14U, 1.0); }
    catch (const std::invalid_argument&) { stale_tick = true; }
    assert(stale_tick);
    assert(monitor.forget("npc-1"));
    return 0;
}

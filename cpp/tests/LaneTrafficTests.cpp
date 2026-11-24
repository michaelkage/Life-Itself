#include "simreality/LaneTraffic.h"

#include <cassert>
#include <stdexcept>
#include <string>
#include <vector>

using namespace simreality;

int main() {
    LaneTrafficCoordinator traffic(2U);
    traffic.configure_lane("main", 1U);
    traffic.configure_lane("side", 2U);
    traffic.advance_tick(1U);

    const auto first = traffic.resolve({
        {"main", "npc-b", 0}, {"main", "npc-a", 0},
        {"side", "npc-c", 0}, {"side", "npc-d", 0}});
    assert(first.tick == 1U);
    assert((first.granted_entity_ids == std::vector<std::string>{"npc-a", "npc-c", "npc-d"}));
    assert((first.denied_entity_ids == std::vector<std::string>{"npc-b"}));
    assert(traffic.has_reservation("main", "npc-a"));
    assert(traffic.available_capacity("main") == 0U);

    traffic.advance_tick(2U);
    const auto second = traffic.resolve({{"main", "npc-b", 0}, {"main", "npc-z", 5}});
    assert((second.granted_entity_ids == std::vector<std::string>{"npc-z"}));
    assert((second.denied_entity_ids == std::vector<std::string>{"npc-b"}));

    // A denied agent accumulates wait credit and wins an equal-priority tie.
    traffic.release("main", "npc-z");
    traffic.advance_tick(3U);
    const auto third = traffic.resolve({{"main", "npc-b", 0}, {"main", "npc-a", 0}});
    assert((third.granted_entity_ids == std::vector<std::string>{"npc-b"}));

    traffic.advance_tick(4U);
    assert(!traffic.has_reservation("main", "npc-b"));
    assert(traffic.available_capacity("main") == 1U);

    const auto fourth = traffic.resolve({{"main", "npc-a", 0}, {"main", "npc-b", 0}});
    assert((fourth.granted_entity_ids == std::vector<std::string>{"npc-a"}));
    assert(traffic.release("main", "npc-a"));
    assert(!traffic.release("main", "npc-a"));

    bool threw = false;
    try { traffic.advance_tick(4U); } catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    threw = false;
    try { traffic.resolve({{"missing", "npc-x", 0}}); }
    catch (const std::out_of_range&) { threw = true; }
    assert(threw);
    threw = false;
    try { traffic.resolve({{"main", "npc-x", 0}, {"main", "npc-x", 1}}); }
    catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    threw = false;
    try { traffic.configure_lane("main", 0U); }
    catch (const std::invalid_argument&) { threw = true; }
    assert(threw);

    LaneTrafficCoordinator no_lease(0U);
    (void)no_lease;
    return 0;
}

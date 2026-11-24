#include "simreality/IntersectionTraffic.h"

#include <cassert>
#include <stdexcept>
#include <string>
#include <vector>

using namespace simreality;

int main() {
    IntersectionTrafficCoordinator traffic(2U);
    traffic.configure_movement({"cross", "north-south", {"center", "south-exit"}});
    traffic.configure_movement({"cross", "east-west", {"center", "west-exit"}});
    traffic.configure_movement({"cross", "north-right", {"north-corner"}});
    traffic.configure_movement({"cross", "south-right", {"south-corner"}});
    traffic.configure_movement({"other", "through", {"center"}});
    traffic.advance_tick(1U);

    const auto first = traffic.resolve({
        {"cross", "north-south", "npc-b", 0},
        {"cross", "east-west", "npc-a", 0},
        {"cross", "north-right", "npc-c", 0},
        {"cross", "south-right", "npc-d", 0}});
    assert((first.granted_entity_ids == std::vector<std::string>{"npc-a", "npc-c", "npc-d"}));
    assert((first.denied_entity_ids == std::vector<std::string>{"npc-b"}));
    assert(traffic.has_reservation("cross", "east-west", "npc-a"));
    assert(traffic.has_reservation("cross", "north-right", "npc-c"));

    // Higher priority wins a contested zone after the existing lease expires.
    traffic.advance_tick(2U);
    const auto second = traffic.resolve({
        {"cross", "north-south", "npc-b", 5},
        {"cross", "east-west", "npc-e", 1}});
    assert(second.granted_entity_ids.empty());
    assert(second.denied_entity_ids.size() == 2U);
    traffic.advance_tick(3U);
    const auto third = traffic.resolve({
        {"cross", "north-south", "npc-b", 5},
        {"cross", "east-west", "npc-e", 1}});
    assert((third.granted_entity_ids == std::vector<std::string>{"npc-b"}));
    assert((third.denied_entity_ids == std::vector<std::string>{"npc-e"}));

    // Multi-zone reservations are atomic and independent intersections do not conflict.
    traffic.release("cross", "npc-b");
    traffic.advance_tick(4U);
    const auto fourth = traffic.resolve({
        {"cross", "north-south", "npc-f", 0},
        {"other", "through", "npc-g", 0}});
    assert((fourth.granted_entity_ids == std::vector<std::string>{"npc-f", "npc-g"}));
    assert(traffic.reservations("cross").size() == 1U);
    assert(traffic.release("cross", "npc-f"));
    assert(!traffic.release("cross", "npc-f"));

    bool threw = false;
    try { traffic.advance_tick(4U); } catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    threw = false;
    try { traffic.resolve({{"cross", "missing", "npc-x", 0}}); }
    catch (const std::out_of_range&) { threw = true; }
    assert(threw);
    threw = false;
    try { traffic.configure_movement({"cross", "invalid", {}}); }
    catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    threw = false;
    try { traffic.resolve({
        {"cross", "north-south", "npc-x", 0},
        {"cross", "east-west", "npc-x", 0}}); }
    catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    threw = false;
    try { IntersectionTrafficCoordinator invalid(0U); (void)invalid; }
    catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    return 0;
}

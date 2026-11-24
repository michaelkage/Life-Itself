cmake_minimum_required(VERSION 3.20)
project(SimulatedRealityCore VERSION 0.1.0 LANGUAGES CXX)

add_library(simreality_core
    src/SimulationClock.cpp
    src/DecisionSystem.cpp
    src/WorldDiagnostics.cpp
    src/RandomStream.cpp
    src/SimulationScheduler.cpp
    src/SimulationRuntime.cpp
    src/Decay.cpp
    src/Gossip.cpp
    src/Ecosystem.cpp
    src/Districts.cpp
    src/Trauma.cpp
    src/Justice.cpp
    src/Reputation.cpp
    src/Fixers.cpp
    src/SimulationWorld.cpp
    src/LifeSystems.cpp
    src/WorldPersistence.cpp
    src/Campaign.cpp
    src/Fluid.cpp
    src/Spatial.cpp
    src/LaneTraffic.cpp
    src/IntersectionTraffic.cpp
    src/RoutePlanning.cpp
    src/TrafficRecovery.cpp
)
target_include_directories(simreality_core PUBLIC include)
target_compile_features(simreality_core PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(simreality_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(simreality_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

option(SIMREALITY_BUILD_TESTS "Build dependency-free core tests" ON)
if(SIMREALITY_BUILD_TESTS)
    enable_testing()
    add_executable(simreality_core_tests tests/CoreTests.cpp)
    target_link_libraries(simreality_core_tests PRIVATE simreality_core)
    add_test(NAME simreality_core_tests COMMAND simreality_core_tests)

    add_executable(simreality_fluid_backend_tests tests/FluidBackendTests.cpp)
    target_link_libraries(simreality_fluid_backend_tests PRIVATE simreality_core)
    add_test(NAME simreality_fluid_backend_tests COMMAND simreality_fluid_backend_tests)

    add_executable(simreality_spatial_tests tests/SpatialTests.cpp)
    target_link_libraries(simreality_spatial_tests PRIVATE simreality_core)
    add_test(NAME simreality_spatial_tests COMMAND simreality_spatial_tests)

    add_executable(simreality_world_spatial_tests tests/WorldSpatialTests.cpp)
    target_link_libraries(simreality_world_spatial_tests PRIVATE simreality_core)
    add_test(NAME simreality_world_spatial_tests COMMAND simreality_world_spatial_tests)

    add_executable(simreality_lane_traffic_tests tests/LaneTrafficTests.cpp)
    target_link_libraries(simreality_lane_traffic_tests PRIVATE simreality_core)
    add_test(NAME simreality_lane_traffic_tests COMMAND simreality_lane_traffic_tests)

    add_executable(simreality_intersection_traffic_tests tests/IntersectionTrafficTests.cpp)
    target_link_libraries(simreality_intersection_traffic_tests PRIVATE simreality_core)
    add_test(NAME simreality_intersection_traffic_tests COMMAND simreality_intersection_traffic_tests)

    add_executable(simreality_world_intersection_tests tests/WorldIntersectionTests.cpp)
    target_link_libraries(simreality_world_intersection_tests PRIVATE simreality_core)
    add_test(NAME simreality_world_intersection_tests COMMAND simreality_world_intersection_tests)

    add_executable(simreality_route_planning_tests tests/RoutePlanningTests.cpp)
    target_link_libraries(simreality_route_planning_tests PRIVATE simreality_core)
    add_test(NAME simreality_route_planning_tests COMMAND simreality_route_planning_tests)

    add_executable(simreality_traffic_recovery_tests tests/TrafficRecoveryTests.cpp)
    target_link_libraries(simreality_traffic_recovery_tests PRIVATE simreality_core)
    add_test(NAME simreality_traffic_recovery_tests COMMAND simreality_traffic_recovery_tests)
endif()

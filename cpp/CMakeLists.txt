cmake_minimum_required(VERSION 3.20)
project(SimulatedRealityCore VERSION 0.1.0 LANGUAGES CXX)

add_library(simreality_core
    src/SimulationClock.cpp
    src/RandomStream.cpp
    src/SimulationScheduler.cpp
    src/SimulationRuntime.cpp
    src/Decay.cpp
    src/Gossip.cpp
    src/DistrictDynamics.cpp
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

    add_executable(simreality_district_tests tests/DistrictDynamicsTests.cpp)
    target_link_libraries(simreality_district_tests PRIVATE simreality_core)
    add_test(NAME simreality_district_tests COMMAND simreality_district_tests)
endif()

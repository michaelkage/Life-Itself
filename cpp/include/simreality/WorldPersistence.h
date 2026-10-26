#pragma once

#include "simreality/SimulationWorld.h"

#include <cstdint>
#include <iosfwd>

namespace simreality {

inline constexpr std::uint32_t kWorldSaveVersion = 15;

// Portable, versioned binary snapshots for deterministic continuation. The format
// uses fixed-width little-endian integers and IEEE-754 doubles; it contains no
// compiler-specific struct dumps or Unreal types.
void save_world(const SimulationWorld& world, std::ostream& output);
[[nodiscard]] SimulationWorld load_world(std::istream& input);

} // namespace simreality

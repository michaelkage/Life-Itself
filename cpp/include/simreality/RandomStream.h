#pragma once

#include <cstdint>

namespace simreality {

// Small, reproducible PRNG for simulation decisions.
// This implementation uses a fixed algorithm rather than std::uniform_*
// distributions, whose mapping details may differ between standard libraries.
// It is not cryptographically secure and must never be used for security.
class RandomStream {
public:
    explicit RandomStream(std::uint64_t seed) noexcept : state_(seed) {}

    [[nodiscard]] std::uint64_t state() const noexcept { return state_; }

    [[nodiscard]] std::uint64_t next_u64() noexcept {
        // SplitMix64: compact, well-tested for non-cryptographic simulation use.
        state_ += 0x9E3779B97F4A7C15ULL;
        std::uint64_t z = state_;
        z = (z ^ (z >> 30U)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27U)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31U);
    }

    // Uniform grid in [0, 1), using the top 53 bits representable by double.
    [[nodiscard]] double unit_interval() noexcept {
        return static_cast<double>(next_u64() >> 11U) * 0x1.0p-53;
    }

    // Returns a value in [0, upper_exclusive). upper_exclusive must be > 0.
    [[nodiscard]] std::uint64_t bounded(std::uint64_t upper_exclusive);

private:
    std::uint64_t state_;
};

} // namespace simreality

#include "simreality/RandomStream.h"

#include <stdexcept>

namespace simreality {

std::uint64_t RandomStream::bounded(std::uint64_t upper_exclusive) {
    if (upper_exclusive == 0U) {
        throw std::invalid_argument("upper_exclusive must be greater than zero");
    }

    // Rejection sampling avoids modulo bias.
    const std::uint64_t threshold = (0U - upper_exclusive) % upper_exclusive;
    for (;;) {
        const std::uint64_t value = next_u64();
        if (value >= threshold) {
            return value % upper_exclusive;
        }
    }
}

} // namespace simreality

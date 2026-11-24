#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <type_traits>

namespace simreality {

// Bounded single-producer/single-consumer transport for trivially-copyable
// commands or immutable render/simulation snapshots. One slot is reserved to
// distinguish full from empty, so usable capacity is Capacity - 1.
template <typename T, std::size_t Capacity>
class SpscRingBuffer {
    static_assert(Capacity >= 2U, "SPSC capacity must be at least two slots");
    static_assert((Capacity & (Capacity - 1U)) == 0U,
                  "SPSC capacity must be a power of two");
    static_assert(std::is_trivially_copyable_v<T>,
                  "SPSC payloads must be trivially copyable");
    static_assert(std::atomic<std::size_t>::is_always_lock_free,
                  "SPSC index atomics must be lock-free on this target");

public:
    SpscRingBuffer() = default;
    SpscRingBuffer(const SpscRingBuffer&) = delete;
    SpscRingBuffer& operator=(const SpscRingBuffer&) = delete;

    [[nodiscard]] bool try_push(const T& value) noexcept {
        const std::size_t head = head_.load(std::memory_order_relaxed);
        const std::size_t next = (head + 1U) & kMask;
        if (next == tail_.load(std::memory_order_acquire)) {
            return false;
        }
        slots_[head] = value;
        head_.store(next, std::memory_order_release);
        return true;
    }

    [[nodiscard]] bool try_pop(T& value) noexcept {
        const std::size_t tail = tail_.load(std::memory_order_relaxed);
        if (tail == head_.load(std::memory_order_acquire)) {
            return false;
        }
        value = slots_[tail];
        tail_.store((tail + 1U) & kMask, std::memory_order_release);
        return true;
    }

    [[nodiscard]] bool empty() const noexcept {
        return tail_.load(std::memory_order_acquire)
            == head_.load(std::memory_order_acquire);
    }

    [[nodiscard]] std::size_t size_approx() const noexcept {
        const std::size_t head = head_.load(std::memory_order_acquire);
        const std::size_t tail = tail_.load(std::memory_order_acquire);
        return (head - tail) & kMask;
    }

    [[nodiscard]] static constexpr std::size_t capacity() noexcept {
        return Capacity - 1U;
    }

private:
    static constexpr std::size_t kMask = Capacity - 1U;
    alignas(64) std::array<T, Capacity> slots_{};
    alignas(64) std::atomic<std::size_t> head_{0U};
    alignas(64) std::atomic<std::size_t> tail_{0U};
};

template <typename Command, std::size_t Capacity = 1024U>
using SimulationCommandBus = SpscRingBuffer<Command, Capacity>;

template <typename Snapshot, std::size_t Capacity = 8U>
using SimulationSnapshotBus = SpscRingBuffer<Snapshot, Capacity>;

} // namespace simreality

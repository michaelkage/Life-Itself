#pragma once

#include "simreality/CoreTypes.h"

#include <string>
#include <utility>
#include <vector>

namespace simreality {

inline constexpr double kReputationFloor = 0.35;
inline constexpr double kBribeWeight = 0.45;
inline constexpr double kExposureWeight = 0.25;
inline constexpr double kFixerMinStanding = 0.2;
inline constexpr double kBetrayalTrustCost = 0.34;
inline constexpr double kCleanDealRecovery = 0.03;
inline constexpr double kTrustResting = 0.5;
inline constexpr double kTrustReversion = 0.015;
inline constexpr double kTrustCeilingFloor = 0.35;
inline constexpr double kTrustCeilingSpan = 0.55;

struct Negotiation {
    bool accepted{false};
    bool bribe_paid{false};
    bool betrayed{false};
    std::string reason{};
    bool squeal_filed{false};
};

struct FixerProfile {
    EntityId entity_id{};
    DistrictId district_id{};
    double standing{0.5};
    double warrants{0.0};
    double bribes_accepted{0.0};
    std::vector<std::string> dealings{};

    [[nodiscard]] double desperation(const District& district) const noexcept;
};

[[nodiscard]] double bribe_greed(double bribe, double warrants) noexcept;
[[nodiscard]] double betrayal_probability(
    double fixer_desperation, double bribe, double warrants, double standing) noexcept;
[[nodiscard]] std::pair<bool, std::string> willingness_to_deal(
    double reputation, const FixerProfile& fixer, const District& district);
[[nodiscard]] Negotiation negotiate(
    FixerProfile& fixer, const District& district, double bribe,
    double reputation, double rng);
[[nodiscard]] std::vector<EntityId> known_betrayers(
    const std::vector<FixerProfile>& fixers);

class FixerNetwork {
public:
    DistrictId district_id{};
    std::vector<FixerProfile> members{};

    [[nodiscard]] double trust() const noexcept;
    [[nodiscard]] double ceiling(const District& district) const noexcept;
    void record_outcome(
        const FixerProfile& fixer, const Negotiation& negotiation, const District& district);
    void daily_update(const District& district, double days = 1.0);
};

} // namespace simreality

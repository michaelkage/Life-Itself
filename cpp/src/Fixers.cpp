#include "simreality/Fixers.h"

#include "simreality/Ecosystem.h"

#include <algorithm>
#include <cmath>

namespace simreality {

double FixerProfile::desperation(const District& district) const noexcept {
    return simreality::desperation_index(district);
}

double bribe_greed(double bribe, double warrants) noexcept {
    return (kBribeWeight * bribe) /
        std::max(1e-9, kBribeWeight * bribe + warrants);
}

double betrayal_probability(
    double fixer_desperation, double bribe, double warrants, double standing) noexcept {
    return std::clamp(fixer_desperation * bribe_greed(bribe, warrants) -
        kExposureWeight * standing, 0.0, 1.0);
}

std::pair<bool, std::string> willingness_to_deal(
    double reputation, const FixerProfile& fixer, const District& district) {
    if (fixer.standing < kFixerMinStanding) {
        return {false, "not established enough to risk dealing"};
    }
    if (reputation < kReputationFloor) {
        return {false, "reputation below the fixer floor"};
    }
    if (desperation_index(district) < 0.3) {
        return {false, "district is too stable for me to be seen helping anyone"};
    }
    return {true, "deal"};
}

Negotiation negotiate(
    FixerProfile& fixer, const District& district, double bribe,
    double reputation, double rng) {
    const auto [willing, refusal_reason] = willingness_to_deal(reputation, fixer, district);
    if (!willing) {
        return {false, false, false, refusal_reason, false};
    }

    const double probability = betrayal_probability(
        fixer.desperation(district), bribe, fixer.warrants, fixer.standing);
    fixer.bribes_accepted += bribe;
    if (rng < probability) {
        fixer.dealings.push_back("betrayed");
        return {true, true, true,
            "took the money and filed an anonymous tip to clear their own warrants -- clean police are on their way",
            true};
    }

    fixer.dealings.push_back("dealt");
    return {true, true, false, "took the deal and kept quiet", false};
}

std::vector<EntityId> known_betrayers(const std::vector<FixerProfile>& fixers) {
    std::vector<EntityId> result;
    for (const FixerProfile& fixer : fixers) {
        if (std::find(fixer.dealings.begin(), fixer.dealings.end(), "betrayed") !=
            fixer.dealings.end()) {
            result.push_back(fixer.entity_id);
        }
    }
    return result;
}

double FixerNetwork::trust() const noexcept {
    if (members.empty()) return 0.0;
    double sum = 0.0;
    for (const FixerProfile& member : members) sum += member.standing;
    return sum / static_cast<double>(members.size());
}

double FixerNetwork::ceiling(const District& district) const noexcept {
    return kTrustCeilingFloor + kTrustCeilingSpan * desperation_index(district);
}

void FixerNetwork::record_outcome(
    const FixerProfile& fixer, const Negotiation& negotiation, const District& district) {
    (void)district;
    if (!negotiation.accepted) return;
    const double cost = negotiation.betrayed
        ? kBetrayalTrustCost * fixer.standing : -kCleanDealRecovery;
    for (FixerProfile& member : members) {
        member.standing = std::clamp(member.standing - cost, kFixerMinStanding, 1.0);
    }
}

void FixerNetwork::daily_update(const District& district, double days) {
    const double max_standing = ceiling(district);
    const double reversion = 1.0 - std::pow(1.0 - kTrustReversion, days);
    for (FixerProfile& member : members) {
        const double pulled = member.standing +
            (kTrustResting - member.standing) * reversion;
        member.standing = std::max(kFixerMinStanding, std::min(max_standing, pulled));
    }
}

} // namespace simreality

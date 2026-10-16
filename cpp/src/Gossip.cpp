#include "simreality/Gossip.h"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace simreality {
namespace {

std::string action_name(ActionTag tag) {
    switch (tag) {
    case ActionTag::InteractionPolite: return "Interaction.Polite";
    case ActionTag::CrimeTheft: return "Crime.Theft";
    case ActionTag::CrimeAssault: return "Crime.Assault";
    case ActionTag::CrimeArmedAssault: return "Crime.ArmedAssault";
    case ActionTag::CrimeVandalism: return "Crime.Vandalism";
    }
    return "Unknown";
}

} // namespace

double jacket_confidence(const Description& d) noexcept {
    double total = 0.0, highest = 0.0;
    for (const auto& [colour, weight] : d.jacket_colour_weights) {
        (void)colour;
        total += weight;
        highest = std::max(highest, weight);
    }
    return total > 0.0 ? highest / total : 0.0;
}

Description merge_descriptions(const Description& a, const Description& b, double fidelity) {
    fidelity = std::clamp(fidelity, 0.0, 1.0);
    const auto na = std::max<std::uint32_t>(1, a.observations);
    const auto nb = static_cast<std::uint32_t>(std::max(1L, std::lround(
        static_cast<double>(std::max<std::uint32_t>(1, b.observations)) * fidelity)));
    const double total = static_cast<double>(na) + static_cast<double>(nb);

    Description out;
    out.height_m = (a.height_m * na + b.height_m * nb) / total;
    out.height_uncertainty_m = std::sqrt(
        a.height_uncertainty_m * a.height_uncertainty_m * na * na +
        b.height_uncertainty_m * b.height_uncertainty_m * nb * nb) / total;
    out.observations = na + nb;
    out.jacket_colour_weights = a.jacket_colour_weights;
    for (const auto& [colour, weight] : b.jacket_colour_weights)
        out.jacket_colour_weights[colour] += weight * fidelity;

    double certainty;
    if (a.masked == b.masked) {
        const double agreement = a.masked_confidence +
            (1.0 - a.masked_confidence) * b.masked_confidence * fidelity;
        certainty = a.masked ? agreement : 1.0 - agreement;
    } else {
        certainty = a.masked_confidence * (1.0 - b.masked_confidence * fidelity);
    }
    out.masked_confidence = std::clamp(certainty, 0.0, 1.0);
    out.masked = out.masked_confidence >= 0.5;
    return out;
}

std::string describe(const Description& d) {
    std::ostringstream out;
    bool first = true;
    auto add = [&](const std::string& part) {
        if (!first) out << ", ";
        out << part;
        first = false;
    };

    if (d.height_uncertainty_m >= 0.25) {
        add(d.height_m >= 1.75 ? "tall-ish" : "average height");
    } else {
        std::ostringstream height;
        height.setf(std::ios::fixed);
        height.precision(2);
        if (d.height_uncertainty_m >= 0.1) height << "about ";
        height << d.height_m << "m";
        add(height.str());
    }

    const double confidence = jacket_confidence(d);
    if (confidence > 0.6) {
        const auto top = std::max_element(d.jacket_colour_weights.begin(),
            d.jacket_colour_weights.end(),
            [](const auto& x, const auto& y) { return x.second < y.second; });
        if (top != d.jacket_colour_weights.end()) add(top->first + " jacket");
    } else if (!d.jacket_colour_weights.empty()) {
        add(confidence < 0.4 ? "dark jacket" : "jacket");
    }
    if (d.masked_confidence > 0.7) add("masked");
    else if (d.masked_confidence > 0.3) add("maybe masked");
    return out.str();
}

Rumour corroborate(const Rumour& a, const Rumour& b) {
    Rumour out;
    out.action_tag = a.action_tag;
    out.target_entity_id = a.target_entity_id == b.target_entity_id ? a.target_entity_id : EntityId{};
    out.description = merge_descriptions(a.description, b.description, b.retention);
    out.retention = std::max(a.retention, b.retention);
    out.district_id = a.district_id.empty() ? b.district_id : a.district_id;
    out.corroborations = a.corroborations + 1;
    return out;
}

std::optional<Rumour> retell(const NPCMemory& memory) {
    const double floor = memory.is_actionable() ? kFloorAttributedRumour : kFloorUnattributedRumour;
    if (memory.retention <= floor) return std::nullopt;

    Rumour out;
    out.action_tag = action_name(memory.action_tag);
    out.target_entity_id = memory.retention >= 0.6 ? memory.target_entity_id : EntityId{};
    out.description = memory.description;
    out.retention = memory.retention;
    return out;
}

Conversation converse(NPC& listener, const NPC& speaker, const DistrictId& district_id) {
    Conversation conversation{speaker.entity_id, listener.entity_id, district_id, {}};
    for (const auto& memory : speaker.memories) {
        auto candidate = retell(memory);
        if (!candidate) continue;
        Rumour rumour = *candidate;
        rumour.district_id = district_id;

        std::optional<std::size_t> match;
        if (!memory.target_entity_id.empty()) {
            for (std::size_t i = 0; i < listener.memories.size(); ++i) {
                if (listener.memories[i].target_entity_id == memory.target_entity_id) match = i;
            }
        }

        if (match) {
            const NPCMemory& existing = listener.memories[*match];
            Rumour prior{action_name(existing.action_tag), existing.target_entity_id,
                existing.description, existing.retention, district_id, 1};
            rumour = corroborate(prior, rumour);
            NPCMemory updated;
            updated.witness_id = listener.entity_id;
            updated.target_entity_id = rumour.target_entity_id;
            updated.initial_impact = std::max(prior.retention, rumour.retention);
            updated.retention = updated.initial_impact;
            updated.timestamp_hour = memory.timestamp_hour;
            updated.action_tag = memory.action_tag;
            updated.description = rumour.description;
            listener.memories[*match] = updated;
        } else {
            NPCMemory received;
            received.witness_id = listener.entity_id;
            received.target_entity_id = rumour.target_entity_id;
            received.initial_impact = rumour.retention;
            received.retention = rumour.retention;
            received.timestamp_hour = memory.timestamp_hour;
            received.action_tag = memory.action_tag;
            received.description = rumour.description;
            listener.memories.push_back(received);
        }
        conversation.transferred.push_back(rumour);
    }
    return conversation;
}

std::string police_response(const Rumour& rumour, const DistrictId& district_id) {
    if (rumour.is_attributable() && rumour.retention >= 0.6)
        return "District " + district_id + ": pursue identification for " + rumour.target_entity_id;
    if (jacket_confidence(rumour.description) > 0.6)
        return "District " + district_id + ": stop and search matching " + describe(rumour.description);
    return "District " + district_id + ": logged, insufficient detail to act on (" +
        describe(rumour.description) + ")";
}

} // namespace simreality

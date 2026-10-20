#include "simreality/Campaign.h"

#include "simreality/WorldPersistence.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <istream>
#include <limits>
#include <ostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

namespace simreality {
namespace {
constexpr std::array<char, 8> kCampaignMagic{{'S', 'R', 'E', 'C', 'A', 'M', 'P', '1'}};
constexpr std::uint32_t kCampaignVersion = 1U;
constexpr std::uint32_t kMaxArchives = 100'000U;
constexpr std::uint32_t kMaxStringBytes = 512U * 1024U * 1024U;

void write_u32(std::ostream& out, std::uint32_t value) {
    for (unsigned int i = 0; i < 4; ++i) {
        out.put(static_cast<char>((value >> (i * 8U)) & 0xffU));
    }
    if (!out) throw std::runtime_error("failed writing campaign snapshot");
}

std::uint32_t read_u32(std::istream& in) {
    std::uint32_t value = 0;
    for (unsigned int i = 0; i < 4; ++i) {
        const int byte = in.get();
        if (byte == std::char_traits<char>::eof()) throw std::runtime_error("truncated campaign snapshot");
        value |= static_cast<std::uint32_t>(static_cast<unsigned char>(byte)) << (i * 8U);
    }
    return value;
}

void write_u64(std::ostream& out, std::uint64_t value) {
    for (unsigned int i = 0; i < 8; ++i) {
        out.put(static_cast<char>((value >> (i * 8U)) & 0xffU));
    }
    if (!out) throw std::runtime_error("failed writing campaign snapshot");
}

std::uint64_t read_u64(std::istream& in) {
    std::uint64_t value = 0;
    for (unsigned int i = 0; i < 8; ++i) {
        const int byte = in.get();
        if (byte == std::char_traits<char>::eof()) throw std::runtime_error("truncated campaign snapshot");
        value |= static_cast<std::uint64_t>(static_cast<unsigned char>(byte)) << (i * 8U);
    }
    return value;
}

void write_string(std::ostream& out, const std::string& value) {
    if (value.size() > kMaxStringBytes
        || value.size() > static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max()))
        throw std::length_error("campaign snapshot field exceeds size limit");
    write_u32(out, static_cast<std::uint32_t>(value.size()));
    out.write(value.data(), static_cast<std::streamsize>(value.size()));
    if (!out) throw std::runtime_error("failed writing campaign snapshot field");
}

std::string read_string(std::istream& in) {
    const std::uint32_t size = read_u32(in);
    if (size > kMaxStringBytes) throw std::length_error("campaign snapshot field exceeds size limit");
    std::string value(size, '\0');
    in.read(value.data(), static_cast<std::streamsize>(size));
    if (!in) throw std::runtime_error("truncated campaign snapshot field");
    return value;
}

std::string snapshot_world(const SimulationWorld& world) {
    std::ostringstream output(std::ios::binary);
    save_world(world, output);
    return output.str();
}

SimulationWorld restore_world(const std::string& snapshot) {
    std::istringstream input(snapshot, std::ios::binary);
    return load_world(input);
}
} // namespace

CampaignCoordinator::CampaignCoordinator(SimulationWorld initial_world)
    : active_world_(std::move(initial_world)) {}

void CampaignCoordinator::begin_first_life(const EntityId& character_id) {
    if (!active_character_id_.empty()) throw std::logic_error("campaign already has a current life");
    if (character_id.empty()) throw std::invalid_argument("character id cannot be empty");
    const auto npc = std::find_if(active_world_.state().npcs.begin(), active_world_.state().npcs.end(),
        [&character_id](const NPC& candidate) { return candidate.entity_id == character_id; });
    if (npc == active_world_.state().npcs.end()) throw std::out_of_range("current life must exist as an NPC");
    active_world_.life_system().register_character(character_id);
    active_character_id_ = character_id;
}

bool CampaignCoordinator::record_death(std::string cause) {
    if (active_character_id_.empty()) throw std::logic_error("campaign has no current life");
    return active_world_.life_system().kill(active_character_id_, active_world_.day_index(), std::move(cause));
}

bool CampaignCoordinator::enter_ghost() {
    if (active_character_id_.empty()) throw std::logic_error("campaign has no current life");
    return active_world_.life_system().enter_ghost(active_character_id_);
}

GhostInfluenceResult CampaignCoordinator::attempt_ghost_influence(
    const EntityId& npc_id, const std::string& action, double hour_of_day) {
    if (active_character_id_.empty()) throw std::logic_error("campaign has no current life");
    return active_world_.attempt_ghost_influence(active_character_id_, npc_id, action, hour_of_day);
}

WorldAdvanceReport CampaignCoordinator::advance(
    double elapsed_hours, Weather visibility_weather, double weather_severity) {
    return active_world_.advance(elapsed_hours, visibility_weather, weather_severity);
}

void CampaignCoordinator::start_new_life(
    const EntityId& character_id, WorldState initial_state, std::uint64_t random_seed) {
    if (active_character_id_.empty()) throw std::logic_error("campaign has no current life");
    if (character_id.empty()) throw std::invalid_argument("character id cannot be empty");
    const auto current = active_world_.life_system().characters().find(active_character_id_);
    if (current == active_world_.life_system().characters().end()
        || (current->second.status != LifeStatus::Spectator && current->second.status != LifeStatus::Ghost))
        throw std::logic_error("a new life requires the current character to have died");
    const LifeCharacter dead_character = current->second;
    if (!active_world_.life_system().archive_character(active_character_id_))
        throw std::logic_error("current life could not be archived");

    ArchivedTimeline archive;
    archive.archive_id = "archive-" + std::to_string(archives_.size() + 1U)
        + "-day-" + std::to_string(active_world_.day_index());
    archive.label = "World at day " + std::to_string(active_world_.day_index());
    archive.character_id = active_character_id_;
    archive.death_day = dead_character.death_day;
    archive.archived_day = active_world_.day_index();
    archive.cause = dead_character.death_cause;
    archive.snapshot = snapshot_world(active_world_);
    archives_.push_back(std::move(archive));

    const auto new_character = std::find_if(initial_state.npcs.begin(), initial_state.npcs.end(),
        [&character_id](const NPC& candidate) { return candidate.entity_id == character_id; });
    if (new_character == initial_state.npcs.end()) {
        NPC resident;
        resident.entity_id = character_id;
        initial_state.npcs.push_back(std::move(resident));
    }
    active_world_ = SimulationWorld(std::move(initial_state), 0.0, random_seed);
    active_world_.life_system().register_character(character_id);
    active_character_id_ = character_id;
}

SimulationWorld CampaignCoordinator::inspect_archive(const std::string& archive_id) const {
    for (const ArchivedTimeline& archive : archives_) {
        if (archive.archive_id == archive_id) return restore_world(archive.snapshot);
    }
    throw std::out_of_range("archive id not found: " + archive_id);
}

void save_campaign(const CampaignCoordinator& campaign, std::ostream& output) {
    output.write(kCampaignMagic.data(), static_cast<std::streamsize>(kCampaignMagic.size()));
    if (!output) throw std::runtime_error("failed writing campaign header");
    write_u32(output, kCampaignVersion);
    write_string(output, campaign.active_character_id_);
    write_string(output, snapshot_world(campaign.active_world_));
    if (campaign.archives_.size() > kMaxArchives) throw std::length_error("too many campaign archives");
    write_u32(output, static_cast<std::uint32_t>(campaign.archives_.size()));
    for (const ArchivedTimeline& archive : campaign.archives_) {
        write_string(output, archive.archive_id);
        write_string(output, archive.label);
        write_string(output, archive.character_id);
        write_u64(output, archive.death_day);
        write_u64(output, archive.archived_day);
        write_string(output, archive.cause);
        write_string(output, archive.snapshot);
    }
}

CampaignCoordinator load_campaign(std::istream& input) {
    std::array<char, kCampaignMagic.size()> magic{};
    input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
    if (!input) throw std::runtime_error("truncated campaign header");
    if (magic != kCampaignMagic) throw std::runtime_error("invalid campaign snapshot magic");
    if (read_u32(input) != kCampaignVersion) throw std::runtime_error("unsupported campaign snapshot version");

    const EntityId active_character_id = read_string(input);
    const std::string active_snapshot = read_string(input);
    CampaignCoordinator campaign(restore_world(active_snapshot));
    campaign.active_character_id_ = active_character_id;
    if (!active_character_id.empty()
        && !campaign.active_world_.life_system().characters().contains(active_character_id))
        throw std::runtime_error("campaign current character is missing from active world");

    const std::uint32_t count = read_u32(input);
    if (count > kMaxArchives) throw std::length_error("too many campaign archives");
    campaign.archives_.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        ArchivedTimeline archive;
        archive.archive_id = read_string(input);
        archive.label = read_string(input);
        archive.character_id = read_string(input);
        archive.death_day = read_u64(input);
        archive.archived_day = read_u64(input);
        archive.cause = read_string(input);
        archive.snapshot = read_string(input);
        if (archive.archive_id.empty() || archive.character_id.empty() || archive.snapshot.empty())
            throw std::runtime_error("invalid campaign archive record");
        // Validate the embedded snapshot now, not only when a viewer opens it.
        (void)restore_world(archive.snapshot);
        campaign.archives_.push_back(std::move(archive));
    }
    return campaign;
}

} // namespace simreality

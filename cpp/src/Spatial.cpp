#include "simreality/Spatial.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace simreality {
namespace {

constexpr long double kMaxQueryCells = 1000000.0L;
constexpr double kPi = 3.14159265358979323846;

double distance_between(SpatialPoint first, SpatialPoint second) {
    return std::hypot(first.x - second.x, first.y - second.y, first.z - second.z);
}

void validate_non_negative(const char* name, double value) {
    if (!std::isfinite(value) || value < 0.0) {
        throw std::invalid_argument(std::string(name) + " must be finite and non-negative");
    }
}

} // namespace

bool SpatialPartition::Cell::operator<(const Cell& other) const noexcept {
    if (x != other.x) return x < other.x;
    if (y != other.y) return y < other.y;
    return z < other.z;
}

SpatialPartition::SpatialPartition(double cell_size) : cell_size_(cell_size) {
    if (!std::isfinite(cell_size_) || cell_size_ <= 0.0) {
        throw std::invalid_argument("spatial cell size must be finite and positive");
    }
}

void SpatialPartition::validate_point(SpatialPoint point) {
    if (!std::isfinite(point.x) || !std::isfinite(point.y) || !std::isfinite(point.z)) {
        throw std::invalid_argument("spatial coordinates must be finite");
    }
}

SpatialPartition::Cell SpatialPartition::cell_for(SpatialPoint point) const {
    validate_point(point);
    const auto coordinate = [this](double value) {
        const long double index = std::floor(
            static_cast<long double>(value) / static_cast<long double>(cell_size_));
        const long double minimum_index =
            static_cast<long double>(std::numeric_limits<std::int64_t>::min());
        const long double maximum_exclusive = -minimum_index;
        if (index < minimum_index || index >= maximum_exclusive) {
            throw std::out_of_range("spatial coordinate exceeds grid index range");
        }
        return static_cast<std::int64_t>(index);
    };
    return {coordinate(point.x), coordinate(point.y), coordinate(point.z)};
}

void SpatialPartition::upsert(const EntityId& entity_id, SpatialPoint position_value) {
    if (entity_id.empty()) {
        throw std::invalid_argument("spatial entity ID must be non-empty");
    }
    const Cell next_cell = cell_for(position_value);
    const auto previous = entity_cells_.find(entity_id);
    if (previous != entity_cells_.end() && !(previous->second < next_cell)
        && !(next_cell < previous->second)) {
        positions_[entity_id] = position_value;
        return;
    }
    if (previous != entity_cells_.end()) {
        auto old_cell = cells_.find(previous->second);
        if (old_cell != cells_.end()) {
            old_cell->second.erase(entity_id);
            if (old_cell->second.empty()) cells_.erase(old_cell);
        }
    }
    positions_[entity_id] = position_value;
    entity_cells_[entity_id] = next_cell;
    cells_[next_cell].insert(entity_id);
}

bool SpatialPartition::erase(const EntityId& entity_id) {
    const auto cell = entity_cells_.find(entity_id);
    if (cell == entity_cells_.end()) return false;
    auto bucket = cells_.find(cell->second);
    if (bucket != cells_.end()) {
        bucket->second.erase(entity_id);
        if (bucket->second.empty()) cells_.erase(bucket);
    }
    entity_cells_.erase(cell);
    positions_.erase(entity_id);
    return true;
}

bool SpatialPartition::contains(const EntityId& entity_id) const {
    return positions_.contains(entity_id);
}

SpatialPoint SpatialPartition::position(const EntityId& entity_id) const {
    const auto found = positions_.find(entity_id);
    if (found == positions_.end()) throw std::out_of_range("spatial entity not found: " + entity_id);
    return found->second;
}

std::vector<EntityId> SpatialPartition::query_radius(
    SpatialPoint center, double radius) const {
    validate_point(center);
    validate_non_negative("query radius", radius);
    const SpatialPoint minimum{center.x - radius, center.y - radius, center.z - radius};
    const SpatialPoint maximum{center.x + radius, center.y + radius, center.z + radius};
    const Cell low = cell_for(minimum);
    const Cell high = cell_for(maximum);
    const long double cell_count =
        (static_cast<long double>(high.x) - static_cast<long double>(low.x) + 1.0L)
        * (static_cast<long double>(high.y) - static_cast<long double>(low.y) + 1.0L)
        * (static_cast<long double>(high.z) - static_cast<long double>(low.z) + 1.0L);
    if (cell_count > kMaxQueryCells) {
        throw std::length_error("spatial radius query spans too many grid cells");
    }

    std::vector<EntityId> result;
    const double tolerance = std::max(1.0, radius) * 1e-12;
    for (std::int64_t x = low.x;; ++x) {
        for (std::int64_t y = low.y;; ++y) {
            for (std::int64_t z = low.z;; ++z) {
                const auto bucket = cells_.find(Cell{x, y, z});
                if (bucket != cells_.end()) {
                    for (const EntityId& entity_id : bucket->second) {
                        if (distance_between(center, positions_.at(entity_id)) <= radius + tolerance) {
                            result.push_back(entity_id);
                        }
                    }
                }
                if (z == high.z) break;
            }
            if (y == high.y) break;
        }
        if (x == high.x) break;
    }
    std::sort(result.begin(), result.end());
    return result;
}

std::vector<EntityId> SpatialPartition::query_aabb(
    SpatialPoint minimum, SpatialPoint maximum) const {
    validate_point(minimum);
    validate_point(maximum);
    if (minimum.x > maximum.x || minimum.y > maximum.y || minimum.z > maximum.z) {
        throw std::invalid_argument("AABB minimum must not exceed its maximum");
    }
    const Cell low = cell_for(minimum);
    const Cell high = cell_for(maximum);
    const long double cell_count =
        (static_cast<long double>(high.x) - static_cast<long double>(low.x) + 1.0L)
        * (static_cast<long double>(high.y) - static_cast<long double>(low.y) + 1.0L)
        * (static_cast<long double>(high.z) - static_cast<long double>(low.z) + 1.0L);
    if (cell_count > kMaxQueryCells) {
        throw std::length_error("spatial AABB query spans too many grid cells");
    }

    std::vector<EntityId> result;
    for (std::int64_t x = low.x;; ++x) {
        for (std::int64_t y = low.y;; ++y) {
            for (std::int64_t z = low.z;; ++z) {
                const auto bucket = cells_.find(Cell{x, y, z});
                if (bucket != cells_.end()) {
                    for (const EntityId& entity_id : bucket->second) {
                        const SpatialPoint point = positions_.at(entity_id);
                        if (point.x >= minimum.x && point.x <= maximum.x
                            && point.y >= minimum.y && point.y <= maximum.y
                            && point.z >= minimum.z && point.z <= maximum.z) {
                            result.push_back(entity_id);
                        }
                    }
                }
                if (z == high.z) break;
            }
            if (y == high.y) break;
        }
        if (x == high.x) break;
    }
    std::sort(result.begin(), result.end());
    return result;
}

VisionAssessment assess_vision(
    SpatialPoint observer_position, SpatialPoint observer_forward,
    SpatialPoint target_position, double maximum_range,
    double field_of_view_radians, bool occluded) {
    SpatialPartition::validate_point(observer_position);
    SpatialPartition::validate_point(observer_forward);
    SpatialPartition::validate_point(target_position);
    validate_non_negative("vision range", maximum_range);
    if (!std::isfinite(field_of_view_radians) || field_of_view_radians < 0.0
        || field_of_view_radians > 2.0 * kPi) {
        throw std::invalid_argument("field of view must be finite and in [0, 2*pi]");
    }
    const SpatialPoint delta{
        target_position.x - observer_position.x,
        target_position.y - observer_position.y,
        target_position.z - observer_position.z};
    const double distance = std::hypot(delta.x, delta.y, delta.z);
    if (distance <= 1e-12) return {!occluded, distance, 0.0};
    const double forward_length = std::hypot(
        observer_forward.x, observer_forward.y, observer_forward.z);
    if (forward_length <= 1e-12) {
        throw std::invalid_argument("vision forward vector must be non-zero");
    }
    const double dot = delta.x * observer_forward.x
        + delta.y * observer_forward.y + delta.z * observer_forward.z;
    const double cosine = std::clamp(dot / (distance * forward_length), -1.0, 1.0);
    const double angle = std::acos(cosine);
    const bool visible = !occluded && distance <= maximum_range
        && angle <= field_of_view_radians * 0.5;
    return {visible, distance, angle};
}

AcousticAssessment assess_sound(
    SpatialPoint source_position, SpatialPoint listener_position,
    double source_power, double maximum_range, double ambient_noise,
    double occlusion_attenuation) {
    SpatialPartition::validate_point(source_position);
    SpatialPartition::validate_point(listener_position);
    validate_non_negative("source power", source_power);
    validate_non_negative("sound range", maximum_range);
    validate_non_negative("ambient noise", ambient_noise);
    if (!std::isfinite(occlusion_attenuation)
        || occlusion_attenuation < 0.0 || occlusion_attenuation > 1.0) {
        throw std::invalid_argument("occlusion attenuation must be finite and in [0, 1]");
    }
    const double distance = distance_between(source_position, listener_position);
    const double intensity = source_power * occlusion_attenuation
        / (1.0 + distance * distance);
    return {distance <= maximum_range && intensity > ambient_noise, distance, intensity};
}

SeparationResult compute_separation(
    SpatialPoint origin, const std::vector<SpatialPoint>& neighbors,
    double preferred_distance, double maximum_force) {
    SpatialPartition::validate_point(origin);
    if (!std::isfinite(preferred_distance) || preferred_distance <= 0.0) {
        throw std::invalid_argument("preferred separation distance must be finite and positive");
    }
    validate_non_negative("maximum separation force", maximum_force);
    SpatialPoint force{};
    std::size_t contributors = 0U;
    for (const SpatialPoint neighbor : neighbors) {
        SpatialPartition::validate_point(neighbor);
        const SpatialPoint delta{
            origin.x - neighbor.x, origin.y - neighbor.y, origin.z - neighbor.z};
        const double distance = std::hypot(delta.x, delta.y, delta.z);
        if (distance <= 1e-12 || distance >= preferred_distance) continue;
        const double strength = (preferred_distance - distance) / preferred_distance;
        force.x += (delta.x / distance) * strength;
        force.y += (delta.y / distance) * strength;
        force.z += (delta.z / distance) * strength;
        ++contributors;
    }
    const double magnitude = std::hypot(force.x, force.y, force.z);
    if (magnitude > maximum_force && magnitude > 0.0) {
        const double scale = maximum_force / magnitude;
        force.x *= scale;
        force.y *= scale;
        force.z *= scale;
    }
    return {force, std::min(magnitude, maximum_force), contributors};
}

} // namespace simreality

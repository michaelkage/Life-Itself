#include "simreality/Spatial.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

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


CollisionAvoidanceResult compute_collision_avoidance(
    const EntityId& subject_id, SpatialPoint subject_position,
    SpatialPoint subject_velocity, double subject_radius,
    const std::vector<MovingBody>& neighbors,
    double prediction_horizon_seconds, double maximum_acceleration) {
    if (subject_id.empty()) {
        throw std::invalid_argument("collision subject ID must not be empty");
    }
    SpatialPartition::validate_point(subject_position);
    SpatialPartition::validate_point(subject_velocity);
    if (!std::isfinite(subject_radius) || subject_radius <= 0.0) {
        throw std::invalid_argument("subject collision radius must be finite and positive");
    }
    validate_non_negative("collision prediction horizon", prediction_horizon_seconds);
    validate_non_negative("maximum collision acceleration", maximum_acceleration);

    std::vector<MovingBody> ordered = neighbors;
    std::sort(ordered.begin(), ordered.end(),
        [](const MovingBody& left, const MovingBody& right) {
            return left.entity_id < right.entity_id;
        });
    for (std::size_t i = 0U; i < ordered.size(); ++i) {
        const MovingBody& body = ordered[i];
        if (body.entity_id.empty() || body.entity_id == subject_id) {
            throw std::invalid_argument("collision neighbors need distinct non-subject IDs");
        }
        if (i > 0U && ordered[i - 1U].entity_id == body.entity_id) {
            throw std::invalid_argument("duplicate collision neighbor ID");
        }
        SpatialPartition::validate_point(body.position);
        SpatialPartition::validate_point(body.velocity);
        if (!std::isfinite(body.collision_radius) || body.collision_radius <= 0.0) {
            throw std::invalid_argument("neighbor collision radius must be finite and positive");
        }
    }

    SpatialPoint accumulated{};
    std::size_t conflicts = 0U;
    double earliest = std::numeric_limits<double>::infinity();
    for (const MovingBody& body : ordered) {
        const SpatialPoint relative_position{
            body.position.x - subject_position.x,
            body.position.y - subject_position.y,
            body.position.z - subject_position.z};
        const SpatialPoint relative_velocity{
            body.velocity.x - subject_velocity.x,
            body.velocity.y - subject_velocity.y,
            body.velocity.z - subject_velocity.z};
        const double speed_squared = relative_velocity.x * relative_velocity.x
            + relative_velocity.y * relative_velocity.y
            + relative_velocity.z * relative_velocity.z;
        double time = 0.0;
        if (speed_squared > 1e-18) {
            const double projection = relative_position.x * relative_velocity.x
                + relative_position.y * relative_velocity.y
                + relative_position.z * relative_velocity.z;
            if (!std::isfinite(speed_squared) || !std::isfinite(projection)) {
                throw std::overflow_error("collision prediction is not representable");
            }
            const double projected = -projection / speed_squared;
            if (!std::isfinite(projected)) {
                throw std::overflow_error("collision prediction time is not representable");
            }
            time = std::clamp(projected, 0.0, prediction_horizon_seconds);
        }
        const SpatialPoint closest{
            relative_position.x + relative_velocity.x * time,
            relative_position.y + relative_velocity.y * time,
            relative_position.z + relative_velocity.z * time};
        const double distance = std::hypot(closest.x, closest.y, closest.z);
        const double required = subject_radius + body.collision_radius;
        if (!std::isfinite(distance) || !std::isfinite(required)) {
            throw std::overflow_error("collision distance or radius is not representable");
        }
        if (distance >= required) continue;

        ++conflicts;
        earliest = std::min(earliest, time);
        SpatialPoint away{-closest.x, -closest.y, -closest.z};
        double away_length = std::hypot(away.x, away.y, away.z);
        if (away_length <= 1e-12) {
            away = {-relative_velocity.x, -relative_velocity.y, -relative_velocity.z};
            away_length = std::hypot(away.x, away.y, away.z);
        }
        if (away_length <= 1e-12) {
            // Stable ID-derived axis for coincident, stationary bodies.
            std::uint64_t hash = 1469598103934665603ULL;
            for (const char raw_ch : body.entity_id) {
                const auto ch = static_cast<unsigned char>(raw_ch);
                hash ^= static_cast<std::uint64_t>(ch);
                hash *= 1099511628211ULL;
            }
            switch (hash % 6U) {
                case 0U: away = {1.0, 0.0, 0.0}; break;
                case 1U: away = {-1.0, 0.0, 0.0}; break;
                case 2U: away = {0.0, 1.0, 0.0}; break;
                case 3U: away = {0.0, -1.0, 0.0}; break;
                case 4U: away = {0.0, 0.0, 1.0}; break;
                default: away = {0.0, 0.0, -1.0}; break;
            }
            away_length = 1.0;
        }
        const double urgency = (required - distance) / required;
        const double time_weight = prediction_horizon_seconds > 0.0
            ? 1.0 - 0.5 * (time / prediction_horizon_seconds) : 1.0;
        const double strength = urgency * time_weight;
        accumulated.x += away.x / away_length * strength;
        accumulated.y += away.y / away_length * strength;
        accumulated.z += away.z / away_length * strength;
        if (!std::isfinite(accumulated.x) || !std::isfinite(accumulated.y)
            || !std::isfinite(accumulated.z)) {
            throw std::overflow_error("collision avoidance force is not representable");
        }
    }

    double magnitude = std::hypot(accumulated.x, accumulated.y, accumulated.z);
    if (magnitude > maximum_acceleration && magnitude > 0.0) {
        const double scale = maximum_acceleration / magnitude;
        accumulated.x *= scale;
        accumulated.y *= scale;
        accumulated.z *= scale;
        magnitude = maximum_acceleration;
    }
    return {accumulated, magnitude, conflicts,
        conflicts == 0U ? 0.0 : earliest};
}

LaneFollowingResult compute_lane_following(
    SpatialPoint position, SpatialPoint current_velocity,
    const std::vector<SpatialPoint>& lane_centerline,
    double lookahead_distance, double desired_speed, double maximum_force) {
    SpatialPartition::validate_point(position);
    SpatialPartition::validate_point(current_velocity);
    validate_non_negative("lane look-ahead distance", lookahead_distance);
    validate_non_negative("lane desired speed", desired_speed);
    validate_non_negative("lane maximum force", maximum_force);
    if (lane_centerline.size() < 2U) {
        throw std::invalid_argument("lane centerline must contain at least two points");
    }
    for (const SpatialPoint point : lane_centerline) {
        SpatialPartition::validate_point(point);
    }

    double best_distance = std::numeric_limits<double>::infinity();
    double best_progress = 0.0;
    std::size_t best_segment = 0U;
    SpatialPoint best_projection{};
    double traversed = 0.0;
    bool found_segment = false;

    for (std::size_t i = 0U; i + 1U < lane_centerline.size(); ++i) {
        const SpatialPoint start = lane_centerline[i];
        const SpatialPoint end = lane_centerline[i + 1U];
        const SpatialPoint delta{end.x - start.x, end.y - start.y, end.z - start.z};
        const double length = std::hypot(delta.x, delta.y, delta.z);
        if (!std::isfinite(length)) {
            throw std::overflow_error("lane segment length is not representable");
        }
        if (length <= 1e-12) continue;
        const double length_squared = length * length;
        if (!std::isfinite(length_squared)) {
            throw std::overflow_error("lane segment projection is not representable");
        }
        const SpatialPoint offset{
            position.x - start.x, position.y - start.y, position.z - start.z};
        const double projection_dot = offset.x * delta.x
            + offset.y * delta.y + offset.z * delta.z;
        if (!std::isfinite(projection_dot)) {
            throw std::overflow_error("lane segment projection is not representable");
        }
        const double t = std::clamp(projection_dot / length_squared, 0.0, 1.0);
        const SpatialPoint projection{
            start.x + delta.x * t,
            start.y + delta.y * t,
            start.z + delta.z * t};
        const double dx = position.x - projection.x;
        const double dy = position.y - projection.y;
        const double dz = position.z - projection.z;
        const double distance = std::hypot(dx, dy, dz);
        if (!std::isfinite(distance)) {
            throw std::overflow_error("lane projection distance is not representable");
        }
        if (!found_segment || distance < best_distance) {
            found_segment = true;
            best_distance = distance;
            best_segment = i;
            best_projection = projection;
            best_progress = traversed + length * t;
        }
        traversed += length;
        if (!std::isfinite(traversed)) {
            throw std::overflow_error("lane centerline length is not representable");
        }
    }
    if (!found_segment) {
        throw std::invalid_argument("lane centerline must contain a non-degenerate segment");
    }

    SpatialPoint target = best_projection;
    double remaining = lookahead_distance;
    for (std::size_t i = best_segment; i + 1U < lane_centerline.size(); ++i) {
        const SpatialPoint end = lane_centerline[i + 1U];
        const SpatialPoint delta{
            end.x - target.x, end.y - target.y, end.z - target.z};
        const double length = std::hypot(delta.x, delta.y, delta.z);
        if (length <= 1e-12) {
            target = end;
            continue;
        }
        if (remaining <= length) {
            const double fraction = remaining / length;
            target = {target.x + delta.x * fraction,
                      target.y + delta.y * fraction,
                      target.z + delta.z * fraction};
            remaining = 0.0;
            break;
        }
        remaining -= length;
        target = end;
    }

    const SpatialPoint direction_delta{
        target.x - position.x, target.y - position.y, target.z - position.z};
    const double direction_length = std::hypot(
        direction_delta.x, direction_delta.y, direction_delta.z);
    SpatialPoint desired_velocity{};
    if (direction_length > 1e-12 && desired_speed > 0.0) {
        const double scale = desired_speed / direction_length;
        desired_velocity = {direction_delta.x * scale,
                            direction_delta.y * scale,
                            direction_delta.z * scale};
    }
    SpatialPoint force{
        desired_velocity.x - current_velocity.x,
        desired_velocity.y - current_velocity.y,
        desired_velocity.z - current_velocity.z};
    if (!std::isfinite(force.x) || !std::isfinite(force.y) || !std::isfinite(force.z)) {
        throw std::overflow_error("lane steering force is not representable");
    }
    const double force_magnitude = std::hypot(force.x, force.y, force.z);
    if (!std::isfinite(force_magnitude)) {
        throw std::overflow_error("lane steering force magnitude is not representable");
    }
    if (force_magnitude > maximum_force && force_magnitude > 0.0) {
        const double scale = maximum_force / force_magnitude;
        force.x *= scale;
        force.y *= scale;
        force.z *= scale;
    }
    return {target, desired_velocity, force,
            best_distance, best_progress, best_segment};
}

} // namespace simreality

#pragma once

#include "simreality/CoreTypes.h"

#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <vector>

namespace simreality {

struct SpatialPoint {
    double x{0.0};
    double y{0.0};
    double z{0.0};
};

struct VisionAssessment {
    bool visible{false};
    double distance{0.0};
    double angle_radians{0.0};
};

struct AcousticAssessment {
    bool audible{false};
    double distance{0.0};
    double received_intensity{0.0};
};

struct SeparationResult {
    SpatialPoint direction{};
    double magnitude{0.0};
    std::size_t contributing_neighbors{0};
};

// Deterministic uniform-grid broadphase. IDs and query results are canonicalized;
// this class owns no entity lifetime or physical coordinates beyond its index.
class SpatialPartition {
public:
    explicit SpatialPartition(double cell_size);

    void upsert(const EntityId& entity_id, SpatialPoint position);
    [[nodiscard]] bool erase(const EntityId& entity_id);
    [[nodiscard]] bool contains(const EntityId& entity_id) const;
    [[nodiscard]] SpatialPoint position(const EntityId& entity_id) const;
    [[nodiscard]] std::vector<EntityId> query_radius(
        SpatialPoint center, double radius) const;
    [[nodiscard]] std::vector<EntityId> query_aabb(
        SpatialPoint minimum, SpatialPoint maximum) const;
    [[nodiscard]] std::size_t size() const noexcept { return positions_.size(); }
    [[nodiscard]] double cell_size() const noexcept { return cell_size_; }
    static void validate_point(SpatialPoint point);

private:
    struct Cell {
        std::int64_t x{0};
        std::int64_t y{0};
        std::int64_t z{0};
        [[nodiscard]] bool operator<(const Cell& other) const noexcept;
    };

    [[nodiscard]] Cell cell_for(SpatialPoint point) const;

    double cell_size_{1.0};
    std::map<EntityId, SpatialPoint> positions_{};
    std::map<EntityId, Cell> entity_cells_{};
    std::map<Cell, std::set<EntityId>> cells_{};
};

[[nodiscard]] VisionAssessment assess_vision(
    SpatialPoint observer_position, SpatialPoint observer_forward,
    SpatialPoint target_position, double maximum_range,
    double field_of_view_radians, bool occluded = false);

[[nodiscard]] AcousticAssessment assess_sound(
    SpatialPoint source_position, SpatialPoint listener_position,
    double source_power, double maximum_range, double ambient_noise,
    double occlusion_attenuation = 1.0);

[[nodiscard]] SeparationResult compute_separation(
    SpatialPoint origin, const std::vector<SpatialPoint>& neighbors,
    double preferred_distance, double maximum_force);

} // namespace simreality

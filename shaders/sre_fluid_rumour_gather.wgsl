// SRE-Fluid ordered evidence gather v0.2.
// One invocation per claim slot. CPU packs each slot's evidence in canonical
// (observed_tick, evidence_id) order; each invocation applies that recurrence
// sequentially so the GPU cannot reorder non-associative confidence updates.
struct ClaimSlot {
    edge_range: vec4<u32>, // start, count, reserved, reserved
    prior: vec4<f32>,      // x = initial confidence
};
struct EvidenceEdge {
    values: vec4<f32>, // strength, source reliability, direction (+1/-1), reserved
};
struct GatherOutput {
    values: vec4<f32>, // confidence, evidence count, reserved, reserved
};
@group(0) @binding(0) var<storage, read> claims: array<ClaimSlot>;
@group(0) @binding(1) var<storage, read> edges: array<EvidenceEdge>;
@group(0) @binding(2) var<storage, read_write> results: array<GatherOutput>;
@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= arrayLength(&claims) || i >= arrayLength(&results)) { return; }
    let slot = claims[i];
    let start = slot.edge_range.x;
    let count = slot.edge_range.y;
    if (start > arrayLength(&edges) || count > arrayLength(&edges) - start) { return; }
    var confidence = clamp(slot.prior.x, 0.0, 1.0);
    for (var offset = 0u; offset < count; offset = offset + 1u) {
        let edge = edges[start + offset].values;
        let influence = clamp(edge.x, 0.0, 1.0) * clamp(edge.y, 0.0, 1.0);
        let target = select(0.0, 1.0, edge.z > 0.0);
        confidence = confidence + (target - confidence) * influence;
    }
    results[i].values = vec4<f32>(clamp(confidence, 0.0, 1.0), f32(count), 0.0, 0.0);
}

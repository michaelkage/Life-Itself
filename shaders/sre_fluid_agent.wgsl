// SRE-Fluid v0.1 — one independent invocation per active agent.
// Input stride: 48 bytes (three vec4<f32>); output stride: 16 bytes.
struct AgentInput {
    identity: vec4<f32>, // x, y, moral shackle, personal stress
    district: vec4<f32>, // overpopulation, shortage, weather, corruption
    rumour: vec4<f32>,   // retention, speaker fidelity, uncertainty, target-known
};
struct AgentOutput {
    values: vec4<f32>, // desperation, trauma tier, transmittable, attribution
};
@group(0) @binding(0) var<storage, read> agents: array<AgentInput>;
@group(0) @binding(1) var<storage, read_write> results: array<AgentOutput>;
const DI_WEIGHT_TOTAL: f32 = 4.6;
const ATTRIBUTION_THRESHOLD: f32 = 0.6;
const ATTRIBUTED_FLOOR: f32 = 0.05;
const UNATTRIBUTED_FLOOR: f32 = 0.01;
@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    // Guard both bindings: a mismatched output allocation must never write OOB.
    if (i >= arrayLength(&agents) || i >= arrayLength(&results)) { return; }
    let a = agents[i];
    let pressure = clamp((a.district.x * 1.2 + a.district.y * 1.5
        + a.district.z * 0.8 + a.district.w * 1.1) / DI_WEIGHT_TOTAL, 0.0, 1.0);
    var personal = 0.0;
    if (a.identity.w >= 0.45) { personal = 2.0; }
    else if (a.identity.w >= 0.10) { personal = 1.0; }
    var environmental = 0.0;
    if (pressure >= 0.90) { environmental = 3.0; }
    else if (pressure >= 0.75) { environmental = 2.0; }
    else if (pressure >= 0.60) { environmental = 1.0; }
    let attributed_input = a.rumour.w >= 0.5 && a.rumour.x >= ATTRIBUTION_THRESHOLD;
    var floor = UNATTRIBUTED_FLOOR;
    if (attributed_input) { floor = ATTRIBUTED_FLOOR; }
    let can_transmit = a.rumour.x > floor;
    let attribution = can_transmit && attributed_input;
    results[i].values = vec4<f32>(pressure, max(personal, environmental),
        select(0.0, 1.0, can_transmit), select(0.0, 1.0, attribution));
}

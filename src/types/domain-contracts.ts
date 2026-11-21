/** Stable boundary contracts between the application and the simulation runtime. */
export type EntityId = string & { readonly __brand: 'EntityId' };
export type EventId = string & { readonly __brand: 'EventId' };
export type CampaignId = string & { readonly __brand: 'CampaignId' };
export type SimulationTick = number & { readonly __brand: 'SimulationTick' };

export type SimulationRunState = 'stopped' | 'paused' | 'running' | 'faulted';
export type SimulationDetailLevel = 'high' | 'medium' | 'low';

export interface WorldClock {
  readonly tick: SimulationTick;
  readonly day: number;
  readonly minuteOfDay: number;
  readonly ticksPerDay: number;
}

export interface WorldEntitySummary {
  readonly id: EntityId;
  readonly displayName: string;
  readonly kind: 'npc' | 'player' | 'business' | 'institution' | 'location';
}

export interface DistrictSummary {
  readonly id: EntityId;
  readonly name: string;
  readonly population: number;
  readonly condition: number;
  readonly activity: 'stable' | 'growing' | 'declining' | 'under_pressure';
}

export interface WorldEventSummary {
  readonly id: EventId;
  readonly tick: SimulationTick;
  readonly category: string;
  readonly title: string;
  readonly description: string;
  readonly involvedEntityIds: readonly EntityId[];
}

export interface WorldSnapshot {
  readonly schemaVersion: 1;
  readonly campaignId: CampaignId;
  readonly revision: number;
  readonly capturedAt: string;
  readonly clock: WorldClock;
  readonly runState: SimulationRunState;
  readonly population: {
    readonly total: number;
    readonly active: number;
    readonly archived: number;
  };
  readonly districts: readonly DistrictSummary[];
  readonly recentEvents: readonly WorldEventSummary[];
}

export type SimulationCommand =
  | { readonly commandId: string; readonly type: 'advance'; readonly ticks: number }
  | { readonly commandId: string; readonly type: 'pause' }
  | { readonly commandId: string; readonly type: 'resume' }
  | { readonly commandId: string; readonly type: 'set_speed'; readonly multiplier: number }
  | { readonly commandId: string; readonly type: 'inspect_entity'; readonly entityId: EntityId };

export interface CommandAccepted {
  readonly commandId: string;
  readonly accepted: true;
  readonly acceptedAtRevision: number;
}

export interface SimulationApiError {
  readonly code: string;
  readonly message: string;
  readonly retryable: boolean;
}

export type Result<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly error: SimulationApiError };

export interface SimulationRuntimePort {
  getWorldSnapshot(signal?: AbortSignal): Promise<Result<WorldSnapshot>>;
  submitCommand(command: SimulationCommand, signal?: AbortSignal): Promise<Result<CommandAccepted>>;
  subscribe(
    listener: (snapshot: WorldSnapshot) => void,
    onError?: (error: SimulationApiError) => void,
  ): () => void;
}

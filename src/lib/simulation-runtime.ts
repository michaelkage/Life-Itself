import type {
  CommandAccepted,
  Result,
  SimulationApiError,
  SimulationCommand,
  SimulationRuntimePort,
  WorldSnapshot,
} from '../types/domain-contracts';

export interface HttpSimulationRuntimeOptions {
  readonly baseUrl: string;
  readonly fetchImpl?: typeof fetch;
  readonly eventSourceFactory?: (url: string) => EventSource;
}

function apiError(code: string, message: string, retryable = false): SimulationApiError {
  return { code, message, retryable };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isWorldSnapshot(value: unknown): value is WorldSnapshot {
  if (!isRecord(value) || value.schemaVersion !== 1) return false;
  if (typeof value.campaignId !== 'string' || !value.campaignId) return false;
  if (!Number.isSafeInteger(value.revision) || (value.revision as number) < 0) return false;
  if (typeof value.capturedAt !== 'string' || !Number.isFinite(Date.parse(value.capturedAt))) return false;
  if (!isRecord(value.clock) || !Number.isSafeInteger(value.clock.tick) ||
      !Number.isSafeInteger(value.clock.day) || !Number.isSafeInteger(value.clock.minuteOfDay) ||
      !Number.isSafeInteger(value.clock.ticksPerDay)) return false;
  if (!['stopped', 'paused', 'running', 'faulted'].includes(String(value.runState))) return false;
  const population = value.population;
  if (!isRecord(population) || !['total', 'active', 'archived'].every(
    (key) => Number.isSafeInteger(population[key]) && (population[key] as number) >= 0,
  )) return false;
  if (!Array.isArray(value.districts) || !Array.isArray(value.recentEvents)) return false;
  return true;
}

function isCommandAccepted(value: unknown): value is CommandAccepted {
  return isRecord(value) && typeof value.commandId === 'string' &&
    value.accepted === true && Number.isSafeInteger(value.acceptedAtRevision) &&
    (value.acceptedAtRevision as number) >= 0;
}

export class HttpSimulationRuntimePort implements SimulationRuntimePort {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly eventSourceFactory: (url: string) => EventSource;

  constructor(options: HttpSimulationRuntimeOptions) {
    const parsed = new URL(options.baseUrl);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      throw new TypeError('Simulation API URL must use HTTP or HTTPS.');
    }
    this.baseUrl = parsed.toString().replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
    this.eventSourceFactory = options.eventSourceFactory ?? ((url) => new EventSource(url));
  }

  async getWorldSnapshot(signal?: AbortSignal): Promise<Result<WorldSnapshot>> {
    try {
      const response = await this.fetchImpl(`${this.baseUrl}/v1/world/snapshot`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal,
      });
      if (!response.ok) return { ok: false, error: await this.readError(response) };
      const payload: unknown = await response.json();
      if (!isWorldSnapshot(payload)) {
        return { ok: false, error: apiError('INVALID_RESPONSE', 'Simulation API returned an invalid world snapshot.') };
      }
      return { ok: true, value: payload };
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return { ok: false, error: apiError('ABORTED', 'The snapshot request was cancelled.') };
      }
      return { ok: false, error: apiError('NETWORK_ERROR', 'Unable to reach the simulation API.', true) };
    }
  }

  async submitCommand(
    command: SimulationCommand,
    signal?: AbortSignal,
  ): Promise<Result<CommandAccepted>> {
    try {
      const response = await this.fetchImpl(`${this.baseUrl}/v1/world/commands`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'Idempotency-Key': command.commandId,
        },
        body: JSON.stringify(command),
        signal,
      });
      if (!response.ok) return { ok: false, error: await this.readError(response) };
      const payload: unknown = await response.json();
      if (!isCommandAccepted(payload) || payload.commandId !== command.commandId) {
        return { ok: false, error: apiError('INVALID_RESPONSE', 'Simulation API returned an invalid command acknowledgement.') };
      }
      return { ok: true, value: payload };
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return { ok: false, error: apiError('ABORTED', 'The command request was cancelled.') };
      }
      return { ok: false, error: apiError('NETWORK_ERROR', 'Unable to submit the simulation command.', true) };
    }
  }

  subscribe(
    listener: (snapshot: WorldSnapshot) => void,
    onError?: (error: SimulationApiError) => void,
  ): () => void {
    const source = this.eventSourceFactory(`${this.baseUrl}/v1/world/stream`);
    let closed = false;
    source.onmessage = (event: MessageEvent<string>) => {
      if (closed) return;
      try {
        const payload: unknown = JSON.parse(event.data);
        if (!isWorldSnapshot(payload)) {
          onError?.(apiError('INVALID_STREAM_EVENT', 'Simulation stream emitted an invalid world snapshot.'));
          return;
        }
        listener(payload);
      } catch {
        onError?.(apiError('INVALID_STREAM_EVENT', 'Simulation stream emitted malformed JSON.'));
      }
    };
    source.onerror = () => {
      if (!closed) onError?.(apiError('STREAM_DISCONNECTED', 'Simulation event stream disconnected.', true));
    };
    return () => {
      if (closed) return;
      closed = true;
      source.close();
    };
  }

  private async readError(response: Response): Promise<SimulationApiError> {
    try {
      const payload: unknown = await response.json();
      if (isRecord(payload) && isRecord(payload.error) &&
          typeof payload.error.code === 'string' && typeof payload.error.message === 'string') {
        return apiError(
          payload.error.code,
          payload.error.message,
          payload.error.retryable === true,
        );
      }
    } catch {
      // Fall through to the stable HTTP error contract.
    }
    return apiError(
      `HTTP_${response.status}`,
      `Simulation API request failed with HTTP ${response.status}.`,
      response.status >= 500 || response.status === 429,
    );
  }
}

export function createConfiguredSimulationRuntime(): HttpSimulationRuntimePort | null {
  const baseUrl = import.meta.env.VITE_SIMULATION_API_URL;
  return baseUrl ? new HttpSimulationRuntimePort({ baseUrl }) : null;
}

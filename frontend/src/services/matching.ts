import {
  matchApi,
  matchHistoryApi,
  matchRunApi,
  type MatchApi,
  type MatchHistoryApi,
  type MatchRunApi,
  type MatchListQuery,
} from "@/api/matches"
import { getApiErrorInfo } from "@/api/errors"
import type {
  MatchCreateInput,
  MatchCreateResult,
  MatchList,
  MatchReport,
  MatchStatusResult,
  MatchRun,
  MatchRunEvent,
} from "@/types/matching"

const terminalStatuses = new Set(["SUCCESS", "FAILED", "CANCELLED"])

function waitForPollInterval(intervalMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Polling aborted", "AbortError"))
      return
    }
    const cleanup = () => signal?.removeEventListener("abort", onAbort)
    const timer = window.setTimeout(() => {
      cleanup()
      resolve()
    }, intervalMs)
    const onAbort = () => {
      window.clearTimeout(timer)
      cleanup()
      reject(new DOMException("Polling aborted", "AbortError"))
    }
    signal?.addEventListener("abort", onAbort, { once: true })
  })
}

export interface PollOptions {
  signal?: AbortSignal
  intervalMs?: number
  timeoutMs?: number
  onStatus?: (status: MatchStatusResult) => void
}

export class MatchService {
  constructor(private readonly api: MatchApi = matchApi) {}

  create(input: MatchCreateInput): Promise<MatchCreateResult> {
    return this.api.create(input)
  }

  list(query?: MatchListQuery): Promise<MatchList> {
    return this.api.list(query)
  }

  get(matchId: number): Promise<MatchReport> {
    return this.api.get(matchId)
  }

  details(matchId: number) {
    return this.api.details(matchId)
  }

  status(matchId: number): Promise<MatchStatusResult> {
    return this.api.status(matchId)
  }

  recalculate(matchId: number): Promise<MatchCreateResult> {
    return this.api.recalculate(matchId)
  }

  async poll(matchId: number, options: PollOptions = {}): Promise<MatchReport> {
    const intervalMs = options.intervalMs ?? 1500
    const timeoutMs = options.timeoutMs ?? 60_000
    const startedAt = Date.now()
    let transientFailures = 0

    while (Date.now() - startedAt < timeoutMs) {
      options.signal?.throwIfAborted()
      try {
        const status = await this.api.status(matchId)
        options.onStatus?.(status)
        transientFailures = 0
        if (terminalStatuses.has(status.status)) {
          return this.api.get(matchId)
        }
      } catch (error) {
        const errorInfo = getApiErrorInfo(error)
        if (!errorInfo.retryable) throw error
        transientFailures += 1
        if (transientFailures > 2) throw error
      }
      await waitForPollInterval(intervalMs, options.signal)
    }
    throw new Error("MATCH_POLL_TIMEOUT")
  }
}

export class MatchHistoryService {
  constructor(private readonly api: MatchHistoryApi = matchHistoryApi) {}

  listAll(offset = 0, limit = 20): Promise<MatchList> {
    return matchApi.list({ offset, limit })
  }

  forJob(jobId: number, offset = 0, limit = 20): Promise<MatchList> {
    return this.api.forJob(jobId, offset, limit)
  }

  forResumeVersion(versionId: number, offset = 0, limit = 20): Promise<MatchList> {
    return this.api.forResumeVersion(versionId, offset, limit)
  }
}

export const matchService = new MatchService()
export const matchHistoryService = new MatchHistoryService()

export interface MatchRunConnectOptions {
  onEvent: (event: MatchRunEvent) => void
  onDisconnected: (attempt: number) => void
  onExhausted: () => void
}

export class MatchRunService {
  constructor(
    private readonly api: MatchRunApi = matchRunApi,
    private readonly eventSourceFactory: (url: string) => EventSource = (url) =>
      new EventSource(url),
  ) {}

  create(input: MatchCreateInput): Promise<MatchRun> {
    return this.api.create(input)
  }

  get(runId: number): Promise<MatchRun> {
    return this.api.get(runId)
  }

  retry(runId: number): Promise<MatchRun> {
    return this.api.retry(runId)
  }

  confirm(runId: number): Promise<MatchRun> {
    return this.api.confirm(runId)
  }

  cancel(runId: number): Promise<MatchRun> {
    return this.api.cancel(runId)
  }

  async connect(runId: number, options: MatchRunConnectOptions): Promise<() => void> {
    let source: EventSource | null = null
    let closed = false
    let reconnects = 0
    let reconnectTimer: number | null = null
    const eventNames: MatchRunEvent["event"][] = [
      "run_started",
      "node_started",
      "node_completed",
      "node_failed",
      "waiting_for_user",
      "run_completed",
      "run_failed",
      "run_cancelled",
    ]
    const open = async (): Promise<void> => {
      if (closed) return
      const url = await this.api.eventUrl(runId)
      if (closed) return
      source = this.eventSourceFactory(url)
      for (const name of eventNames) {
        source.addEventListener(name, (rawEvent) => {
          const event = JSON.parse((rawEvent as MessageEvent<string>).data) as MatchRunEvent
          options.onEvent(event)
        })
      }
      source.onerror = () => {
        source?.close()
        source = null
        if (closed) return
        reconnects += 1
        options.onDisconnected(reconnects)
        if (reconnects > 3) {
          options.onExhausted()
          return
        }
        reconnectTimer = window.setTimeout(() => void open(), reconnects * 500)
      }
    }
    await open()
    return () => {
      closed = true
      source?.close()
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    }
  }
}

export const matchRunService = new MatchRunService()

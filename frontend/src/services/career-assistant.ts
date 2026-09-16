import {
  createCareerAssistantQA,
  careerAssistantEventUrl,
  getCareerAssistantQA,
  listCareerAssistantQA,
} from "@/api/career-assistant"
import type {
  CareerAssistantQA,
  CareerAssistantQAEvent,
  CareerAssistantQAList,
  CareerAssistantQACreateInput,
} from "@/types/career-assistant"

export interface CareerAssistantConnectOptions {
  onEvent: (event: CareerAssistantQAEvent) => void
  onDisconnected: (attempt: number) => void
  onExhausted: () => void
}

export class CareerAssistantQAService {
  constructor(
    private readonly eventSourceFactory: (url: string) => EventSource = (url) =>
      new EventSource(url),
  ) {}

  create(input: CareerAssistantQACreateInput): Promise<CareerAssistantQA> {
    return createCareerAssistantQA(input)
  }

  get(runId: number): Promise<CareerAssistantQA> {
    return getCareerAssistantQA(runId)
  }

  list(offset = 0, limit = 20): Promise<CareerAssistantQAList> {
    return listCareerAssistantQA(offset, limit)
  }

  async connect(
    runId: number,
    options: CareerAssistantConnectOptions,
  ): Promise<() => void> {
    let source: EventSource | null = null
    let closed = false
    let reconnects = 0
    let reconnectTimer: number | null = null
    const eventNames: CareerAssistantQAEvent["event"][] = [
      "run_started",
      "node_started",
      "node_completed",
      "node_failed",
      "run_completed",
      "run_failed",
      "run_cancelled",
    ]

    const open = async (): Promise<void> => {
      if (closed) return
      const url = await careerAssistantEventUrl(runId)
      if (closed) return
      source = this.eventSourceFactory(url)
      for (const name of eventNames) {
        source.addEventListener(name, (rawEvent) => {
          try {
            const event = JSON.parse(
              (rawEvent as MessageEvent<string>).data,
            ) as CareerAssistantQAEvent
            options.onEvent(event)
          } catch {
            // Skip malformed payloads — the persisted state remains the source of truth.
          }
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

export const careerAssistantService = new CareerAssistantQAService()

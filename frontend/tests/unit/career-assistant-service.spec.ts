import { beforeEach, describe, expect, it, vi } from "vitest"

import type { CareerAssistantQAEvent } from "@/types/career-assistant"

const careerAssistantEventUrl = vi.fn()
const createCareerAssistantQA = vi.fn()

vi.mock("@/api/career-assistant", () => ({
  createCareerAssistantQA,
  getCareerAssistantQA: vi.fn(),
  listCareerAssistantQA: vi.fn(),
  careerAssistantEventUrl,
}))

type EventListener = (event: MessageEvent<string>) => void

class FakeEventSource {
  private listeners = new Map<string, EventListener[]>()
  onerror: (() => void) | null = null
  close = vi.fn()

  constructor(public readonly url: string) {}

  addEventListener(type: string, listener: EventListener): void {
    const list = this.listeners.get(type) ?? []
    list.push(listener)
    this.listeners.set(type, list)
  }

  dispatch(type: string, data: string): void {
    const listeners = this.listeners.get(type) ?? []
    for (const listener of listeners) {
      listener(new MessageEvent(type, { data }))
    }
  }
}

describe("CareerAssistantQAService", () => {
  beforeEach(() => {
    careerAssistantEventUrl.mockReset()
    createCareerAssistantQA.mockReset()
  })

  it("uses a scoped ticket URL and closes EventSource on disconnect", async () => {
    careerAssistantEventUrl.mockResolvedValue(
      "/api/career-assistant/qa/7/events?ticket=scoped",
    )
    const source = new FakeEventSource("about:blank")
    const factory = vi.fn(() => source as unknown as EventSource)
    const { CareerAssistantQAService } = await import("@/services/career-assistant")
    const service = new CareerAssistantQAService(factory)
    const received: CareerAssistantQAEvent[] = []
    const disconnect = await service.connect(7, {
      onEvent: (event) => received.push(event),
      onDisconnected: vi.fn(),
      onExhausted: vi.fn(),
    })

    source.dispatch(
      "run_completed",
      JSON.stringify({
        id: 11,
        event: "run_completed",
        run_id: 7,
        node: null,
        status: "SUCCEEDED",
        timestamp: "2026-07-22T00:00:00Z",
        duration_ms: 1234,
        summary: {},
        error_code: null,
        error_message: null,
        answer: "Python is a versatile language.",
        citations: [
          {
            source_type: "knowledge",
            source_id: 1,
            document_id: 1,
            title: "Career Guide",
            category: "guide",
            chunk_index: 0,
            chunk_text: "Python is versatile.",
            quote: "Python is versatile.",
            page_number: null,
            paragraph_index: 0,
            score: 0.92,
          },
        ],
      }),
    )

    expect(careerAssistantEventUrl).toHaveBeenCalledWith(7)
    expect(received).toHaveLength(1)
    expect(received[0]?.event).toBe("run_completed")
    expect(received[0]?.answer).toBe("Python is a versatile language.")
    expect(received[0]?.citations).toHaveLength(1)
    disconnect()
    expect(source.close).toHaveBeenCalled()
  })

  it("skips malformed payloads without throwing", async () => {
    careerAssistantEventUrl.mockResolvedValue(
      "/api/career-assistant/qa/8/events?ticket=scoped",
    )
    const source = new FakeEventSource("about:blank")
    const { CareerAssistantQAService } = await import("@/services/career-assistant")
    const service = new CareerAssistantQAService(
      () => source as unknown as EventSource,
    )
    const received: CareerAssistantQAEvent[] = []
    const disconnect = await service.connect(8, {
      onEvent: (event) => received.push(event),
      onDisconnected: vi.fn(),
      onExhausted: vi.fn(),
    })

    source.dispatch("run_started", "not-json")

    // Malformed JSON must be skipped silently.
    expect(received).toHaveLength(0)

    // A valid JSON payload is delivered to the onEvent callback.
    source.dispatch(
      "run_started",
      JSON.stringify({ event: "run_started" }),
    )
    expect(received).toHaveLength(1)
    disconnect()
  })

  it("create forwards scope to the API create function", async () => {
    createCareerAssistantQA.mockResolvedValue({
      id: 42,
      user_id: 1,
      question: "What are my skills?",
      answer: null,
      status: "PENDING",
      citations: [],
      error_code: null,
      error_message: null,
      created_at: "2026-07-22T00:00:00Z",
      finished_at: null,
    })
    const { CareerAssistantQAService } = await import("@/services/career-assistant")
    const service = new CareerAssistantQAService()
    await service.create({ question: "What are my skills?", scope: "personal" })
    expect(createCareerAssistantQA).toHaveBeenCalledWith({
      question: "What are my skills?",
      scope: "personal",
    })
  })

  it("create omits scope when not provided (defaults to auto on backend)", async () => {
    createCareerAssistantQA.mockResolvedValue({
      id: 43,
      user_id: 1,
      question: "What is Python?",
      answer: null,
      status: "PENDING",
      citations: [],
      error_code: null,
      error_message: null,
      created_at: "2026-07-22T00:00:00Z",
      finished_at: null,
    })
    const { CareerAssistantQAService } = await import("@/services/career-assistant")
    const service = new CareerAssistantQAService()
    await service.create({ question: "What is Python?" })
    expect(createCareerAssistantQA).toHaveBeenCalledWith({
      question: "What is Python?",
    })
  })
})

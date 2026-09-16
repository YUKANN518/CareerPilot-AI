import { describe, expect, it, vi } from "vitest"

import { MatchRunService } from "@/services/matching"
import type { MatchRunEvent } from "@/types/matching"

class FakeEventSource {
  listeners = new Map<string, (event: MessageEvent<string>) => void>()
  onerror: (() => void) | null = null
  close = vi.fn()

  addEventListener(name: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.set(name, listener as (event: MessageEvent<string>) => void)
  }
}

describe("MatchRunService", () => {
  it("uses a scoped ticket URL and closes EventSource", async () => {
    const source = new FakeEventSource()
    const api = {
      create: vi.fn(),
      get: vi.fn(),
      retry: vi.fn(),
      confirm: vi.fn(),
      cancel: vi.fn(),
      eventUrl: vi.fn().mockResolvedValue("/api/match-runs/1/events?ticket=scoped"),
    }
    const received: MatchRunEvent[] = []
    const service = new MatchRunService(api, () => source as unknown as EventSource)
    const disconnect = await service.connect(1, {
      onEvent: (event) => received.push(event),
      onDisconnected: vi.fn(),
      onExhausted: vi.fn(),
    })
    source.listeners.get("node_started")?.(
      new MessageEvent("node_started", {
        data: JSON.stringify({
          id: 2,
          event: "node_started",
          run_id: 1,
          node: "load_inputs",
          status: "RUNNING",
          timestamp: "2026-07-18T00:00:00Z",
          duration_ms: null,
          summary: {},
          error_code: null,
          error_message: null,
          report_id: null,
        }),
      }),
    )
    expect(received[0]?.node).toBe("load_inputs")
    disconnect()
    expect(source.close).toHaveBeenCalled()
  })
})

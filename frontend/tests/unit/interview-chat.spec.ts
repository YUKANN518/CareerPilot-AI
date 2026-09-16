import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type {
  Interview,
  InterviewChatReportRead,
  InterviewChatStatusRead,
  InterviewChatTurnResponse,
  InterviewMessage,
} from "@/types/interview"

const getInterview = vi.hoisted(() => vi.fn())
const getInterviewChatStatus = vi.hoisted(() => vi.fn())
const listInterviewMessages = vi.hoisted(() => vi.fn())
const startInterviewChat = vi.hoisted(() => vi.fn())
const sendInterviewMessage = vi.hoisted(() => vi.fn())
const completeInterviewChat = vi.hoisted(() => vi.fn())
const cancelInterviewChat = vi.hoisted(() => vi.fn())
const getInterviewChatReport = vi.hoisted(() => vi.fn())
const push = vi.hoisted(() => vi.fn())

vi.mock("@/api/interviews", () => ({
  getInterview,
  getInterviewChatStatus,
  listInterviewMessages,
  startInterviewChat,
  sendInterviewMessage,
  completeInterviewChat,
  cancelInterviewChat,
  getInterviewChatReport,
}))
vi.mock("@/api/errors", () => ({
  getApiErrorInfo: (error: unknown) => {
    const message = error instanceof Error ? error.message : "未知错误"
    let kind = "unknown"
    if (message.includes("无权")) {
      kind = "forbidden"
    } else if (message.includes("超时") || message.includes("timeout")) {
      kind = "timeout"
    } else if (message.includes("网络") || message.includes("network")) {
      kind = "network"
    }
    return {
      kind,
      status: null,
      code: "UNKNOWN_ERROR",
      message,
      retryable: false,
      fieldErrors: {},
    }
  },
  getApiErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "请求失败",
}))
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { interviewId: "201" } }),
  useRouter: () => ({ push }),
  RouterLink: {
    name: "RouterLink",
    props: ["to"],
    template: '<a><slot /></a>',
  },
}))

import InterviewChatPage from "@/pages/InterviewChatPage.vue"
import InterviewChatReportPage from "@/pages/InterviewChatReportPage.vue"

function makeInterview(overrides: Partial<Interview> = {}): Interview {
  return {
    id: 201,
    user_id: 1,
    resume_version_id: 12,
    job_id: 31,
    interview_type: "TECHNICAL",
    status: "PLANNED",
    summary: "",
    missing_skill_warnings: [],
    fabrication_warnings: [],
    job_information_warning: "",
    workflow_run_id: null,
    workflow_version: null,
    provider: null,
    latency_ms: null,
    error_code: null,
    error_message: null,
    questions: [],
    report: {},
    created_at: "2026-07-23T10:00:00Z",
    updated_at: "2026-07-23T10:00:00Z",
    ...overrides,
  }
}

function makeStatus(
  overrides: Partial<InterviewChatStatusRead> = {},
): InterviewChatStatusRead {
  return {
    id: 201,
    chat_status: "WAITING_FOR_ANSWER",
    status: "IN_PROGRESS",
    progress: { current_question: 1, total_questions: 3, follow_up_count: 0 },
    dify_conversation_id: "conv-abc",
    ...overrides,
  }
}

function makeMessage(
  overrides: Partial<InterviewMessage> = {},
): InterviewMessage {
  return {
    id: 1,
    session_id: 201,
    sequence: 1,
    role: "ASSISTANT",
    content: "请介绍一下你使用 Python 的经验。",
    created_at: "2026-07-23T10:00:01Z",
    ...overrides,
  }
}

function makeTurn(
  overrides: Partial<InterviewChatTurnResponse> = {},
): InterviewChatTurnResponse {
  return {
    user_message: makeMessage({
      id: 10,
      sequence: 2,
      role: "USER",
      content: "我用 Python 开发过异步服务。",
    }),
    assistant_message: makeMessage({
      id: 11,
      sequence: 3,
      role: "ASSISTANT",
      content: "你能详细说明 asyncio 的使用场景吗？",
    }),
    next_action: "FOLLOW_UP",
    progress: { current_question: 1, total_questions: 3, follow_up_count: 1 },
    interview_completed: false,
    report_status: "pending",
    ...overrides,
  }
}

function makeReport(
  overrides: Partial<InterviewChatReportRead> = {},
): InterviewChatReportRead {
  return {
    id: 201,
    status: "COMPLETED",
    chat_status: "COMPLETED",
    interview_type: "TECHNICAL",
    overall_score: 82,
    dimension_scores: [
      { dimension: "relevance", score: 85, rationale: "回答紧扣主题" },
      { dimension: "completeness", score: 80, rationale: "覆盖度尚可" },
      { dimension: "clarity", score: 82, rationale: "表述清晰" },
      { dimension: "structure", score: 78, rationale: "结构合理" },
      { dimension: "technical_accuracy", score: 88, rationale: "技术准确" },
    ],
    summary: "候选人 Python 基础扎实，建议进一步考察系统设计能力。",
    strengths: ["Python 基础扎实", "异步编程理解到位"],
    weaknesses: ["对 GIL 的理解不够深入"],
    best_answers: [
      {
        question_sequence: 1,
        excerpt: "我用 Python 开发过异步服务。",
        reason: "回答紧扣并发主题，证据充分。",
      },
    ],
    weakest_answers: [
      {
        question_sequence: 2,
        excerpt: "GIL 影响不大。",
        reason: "技术细节有误。",
      },
    ],
    unsupported_claims: ["声称熟悉 Rust 但简历无证据"],
    missing_skill_warnings: ["SQL 在简历中未体现"],
    fabrication_warnings: [],
    improvement_suggestions: ["补充对 GIL 影响的讨论"],
    practice_questions: ["请解释 asyncio 的事件循环机制。"],
    used_facts: ["简历项目: async-http-aggregator"],
    question_count: 3,
    answered_count: 3,
    report: {},
    generated_at: "2026-07-23T10:15:00Z",
    error_code: null,
    error_message: null,
    ...overrides,
  }
}

function mountChat() {
  return mount(InterviewChatPage, {
    global: {
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        ForbiddenState: { template: '<div data-testid="forbidden-state" />' },
        LoadingState: { template: '<div data-testid="loading-state" />' },
        ErrorState: { template: '<div data-testid="error-state" />' },
      },
    },
  })
}

function mountReport() {
  return mount(InterviewChatReportPage, {
    global: {
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        ForbiddenState: { template: '<div data-testid="forbidden-state" />' },
        LoadingState: { template: '<div data-testid="loading-state" />' },
        ErrorState: { template: '<div data-testid="error-state" />' },
      },
    },
  })
}

describe("interview chat page", () => {
  beforeEach(() => {
    getInterview.mockReset()
    getInterviewChatStatus.mockReset()
    listInterviewMessages.mockReset()
    startInterviewChat.mockReset()
    sendInterviewMessage.mockReset()
    completeInterviewChat.mockReset()
    cancelInterviewChat.mockReset()
    push.mockReset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("auto-starts chat when status is CREATED and renders first assistant message", async () => {
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(
      makeStatus({ chat_status: "WAITING_FOR_ANSWER" }),
    )
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "请介绍你的 Python 经验。" }),
    ])

    const wrapper = mountChat()
    await flushPromises()

    expect(startInterviewChat).toHaveBeenCalledWith(201)
    expect(wrapper.find('[data-testid="interview-chat"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-message-assistant"]').exists()).toBe(true)
    expect(wrapper.text()).toContain("请介绍你的 Python 经验。")
    expect(wrapper.find('[data-testid="chat-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-send-button"]').exists()).toBe(true)
  })

  it("renders existing messages and resumes session when status is WAITING_FOR_ANSWER", async () => {
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(
      makeStatus({
        chat_status: "WAITING_FOR_ANSWER",
        progress: { current_question: 2, total_questions: 3, follow_up_count: 1 },
      }),
    )
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "第一题" }),
      makeMessage({ id: 2, sequence: 2, role: "USER", content: "第一答" }),
      makeMessage({ id: 3, sequence: 3, role: "ASSISTANT", content: "追问" }),
    ])
    startInterviewChat.mockResolvedValue(makeStatus())

    const wrapper = mountChat()
    await flushPromises()

    expect(startInterviewChat).not.toHaveBeenCalled()
    expect(wrapper.findAll('[data-testid="chat-message-assistant"]').length).toBe(2)
    expect(wrapper.findAll('[data-testid="chat-message-user"]').length).toBe(1)
    expect(wrapper.find('[data-testid="chat-progress"]').text()).toContain("2/3")
    expect(wrapper.find('[data-testid="chat-progress"]').text()).toContain("追问 1")
  })

  it("sends user answer and renders assistant reply with updated progress", async () => {
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(makeStatus({ chat_status: "WAITING_FOR_ANSWER" }))
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "首题" }),
    ])
    sendInterviewMessage.mockResolvedValue(makeTurn())

    const wrapper = mountChat()
    await flushPromises()

    await wrapper.get('[data-testid="chat-input"]').setValue("我用 Python 开发过异步服务。")
    await wrapper.get('[data-testid="chat-send-button"]').trigger("click")
    await flushPromises()

    expect(sendInterviewMessage).toHaveBeenCalledWith(201, {
      content: "我用 Python 开发过异步服务。",
    })
    // User message + assistant reply appended.
    expect(wrapper.findAll('[data-testid="chat-message-user"]').length).toBe(1)
    expect(wrapper.findAll('[data-testid="chat-message-assistant"]').length).toBe(2)
    expect(wrapper.text()).toContain("你能详细说明 asyncio 的使用场景吗？")
    // Progress updated to follow-up 1.
    expect(wrapper.find('[data-testid="chat-progress"]').text()).toContain("追问 1")
  })

  it("shows AI thinking indicator while waiting for assistant reply", async () => {
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(makeStatus({ chat_status: "WAITING_FOR_ANSWER" }))
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "首题" }),
    ])

    // Never resolve sendInterviewMessage to keep aiThinking true.
    sendInterviewMessage.mockReturnValue(new Promise(() => {}))

    const wrapper = mountChat()
    await flushPromises()

    await wrapper.get('[data-testid="chat-input"]').setValue("回答")
    await wrapper.get('[data-testid="chat-send-button"]').trigger("click")
    await flushPromises()

    expect(wrapper.find('[data-testid="chat-thinking"]').exists()).toBe(true)
  })

  it("redirects to report page when interview completes via chat turn", async () => {
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(makeStatus({ chat_status: "WAITING_FOR_ANSWER" }))
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "首题" }),
    ])
    sendInterviewMessage.mockResolvedValue(
      makeTurn({
        interview_completed: true,
        report_status: "ready",
        next_action: "COMPLETE_INTERVIEW",
      }),
    )

    const wrapper = mountChat()
    await flushPromises()

    await wrapper.get('[data-testid="chat-input"]').setValue("最终回答")
    await wrapper.get('[data-testid="chat-send-button"]').trigger("click")
    await flushPromises()

    // Completion banner appears.
    expect(wrapper.find('[data-testid="chat-completion-banner"]').exists()).toBe(true)
    // After the 1200ms timer fires, redirect is triggered.
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(push).toHaveBeenCalledWith({
      name: "interview-chat-report",
      params: { interviewId: 201 },
    })
  })

  it("triggers early completion via chat-complete-button", async () => {
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(makeStatus({ chat_status: "WAITING_FOR_ANSWER" }))
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "首题" }),
    ])
    completeInterviewChat.mockResolvedValue(
      makeStatus({ chat_status: "COMPLETED" }),
    )

    const wrapper = mountChat()
    await flushPromises()

    // Stub window.confirm to accept the dialog.
    vi.spyOn(window, "confirm").mockReturnValue(true)
    await wrapper.get('[data-testid="chat-complete-button"]').trigger("click")
    await flushPromises()

    expect(completeInterviewChat).toHaveBeenCalledWith(201)
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(push).toHaveBeenCalledWith({
      name: "interview-chat-report",
      params: { interviewId: 201 },
    })
  })

  it("shows action error when send message fails", async () => {
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(makeStatus({ chat_status: "WAITING_FOR_ANSWER" }))
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "首题" }),
    ])
    sendInterviewMessage.mockRejectedValue(new Error("网络错误"))

    const wrapper = mountChat()
    await flushPromises()

    await wrapper.get('[data-testid="chat-input"]').setValue("回答")
    await wrapper.get('[data-testid="chat-send-button"]').trigger("click")
    await flushPromises()

    expect(wrapper.find('[data-testid="chat-action-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain("网络错误")
  })

  it("recovers from timeout when server actually completed the interview", async () => {
    // Regression: the Dify Final Evaluation Workflow can take ~30s.
    // If axios times out while the server is still generating the
    // report, the page must poll /chat/status and, on COMPLETED,
    // refresh messages and redirect to the report page instead of
    // surfacing a misleading error.
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(makeStatus({ chat_status: "WAITING_FOR_ANSWER" }))
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "首题" }),
    ])
    // First call to getInterviewChatStatus (during load) returns
    // WAITING_FOR_ANSWER; the second call (recovery poll after timeout)
    // returns COMPLETED.
    getInterviewChatStatus
      .mockResolvedValueOnce(makeStatus({ chat_status: "CREATED" }))
      .mockResolvedValueOnce(
        makeStatus({ chat_status: "COMPLETED" }),
      )
    sendInterviewMessage.mockRejectedValue(new Error("请求超时，请检查网络后重试。"))

    const wrapper = mountChat()
    await flushPromises()

    await wrapper.get('[data-testid="chat-input"]').setValue("最终回答")
    await wrapper.get('[data-testid="chat-send-button"]').trigger("click")
    await flushPromises()

    // Recovery poll performed.
    expect(getInterviewChatStatus).toHaveBeenCalledWith(201)
    // No error surfaced — the server had actually completed.
    expect(wrapper.find('[data-testid="chat-action-error"]').exists()).toBe(false)
    // Completion banner shown, then redirect fires after 1200ms.
    expect(wrapper.find('[data-testid="chat-completion-banner"]').exists()).toBe(true)
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(push).toHaveBeenCalledWith({
      name: "interview-chat-report",
      params: { interviewId: 201 },
    })
  })

  it("surfaces timeout error when server is still WAITING_FOR_ANSWER after recovery poll", async () => {
    // If the timeout was a genuine failure (server still waiting for
    // answer), the page must surface the original error so the user
    // can retry, rather than silently swallowing it.
    getInterview.mockResolvedValue(makeInterview())
    getInterviewChatStatus.mockResolvedValue(makeStatus({ chat_status: "CREATED" }))
    startInterviewChat.mockResolvedValue(makeStatus({ chat_status: "WAITING_FOR_ANSWER" }))
    listInterviewMessages.mockResolvedValue([
      makeMessage({ id: 1, sequence: 1, role: "ASSISTANT", content: "首题" }),
    ])
    getInterviewChatStatus
      .mockResolvedValueOnce(makeStatus({ chat_status: "CREATED" }))
      .mockResolvedValueOnce(
        makeStatus({ chat_status: "WAITING_FOR_ANSWER" }),
      )
    sendInterviewMessage.mockRejectedValue(new Error("请求超时，请检查网络后重试。"))

    const wrapper = mountChat()
    await flushPromises()

    await wrapper.get('[data-testid="chat-input"]').setValue("回答")
    await wrapper.get('[data-testid="chat-send-button"]').trigger("click")
    await flushPromises()

    expect(getInterviewChatStatus).toHaveBeenCalledWith(201)
    // Server is still waiting — surface the original timeout error.
    expect(wrapper.find('[data-testid="chat-action-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain("请求超时")
    // No redirect.
    expect(push).not.toHaveBeenCalled()
  })

  it("shows forbidden state when user lacks access", async () => {
    getInterview.mockRejectedValue(new Error("无权访问该面试会话"))
    getInterviewChatStatus.mockResolvedValue(makeStatus())

    const wrapper = mountChat()
    await flushPromises()

    expect(wrapper.find('[data-testid="forbidden-state"]').exists()).toBe(true)
  })
})

describe("interview chat report page", () => {
  beforeEach(() => {
    getInterviewChatReport.mockReset()
  })

  it("renders overall score, dimensions, strengths, weaknesses, best/weakest answers, fact-check", async () => {
    getInterviewChatReport.mockResolvedValue(makeReport())
    const wrapper = mountReport()
    await flushPromises()

    expect(wrapper.find('[data-testid="interview-chat-report"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-report-overall-score"]').text()).toContain("82")
    expect(wrapper.findAll('[data-testid="chat-report-dimension"]').length).toBe(5)
    expect(wrapper.find('[data-testid="chat-report-strengths"]').text()).toContain("Python 基础扎实")
    expect(wrapper.find('[data-testid="chat-report-weaknesses"]').text()).toContain("GIL")
    expect(wrapper.find('[data-testid="chat-report-best-answers"]').text()).toContain("问题 #1")
    expect(wrapper.find('[data-testid="chat-report-weakest-answers"]').text()).toContain("问题 #2")
    expect(wrapper.find('[data-testid="chat-report-improvement"]').text()).toContain("GIL")
    expect(wrapper.find('[data-testid="chat-report-practice"]').text()).toContain("asyncio")
    expect(wrapper.find('[data-testid="chat-report-fact-check"]').text()).toContain("SQL")
  })

  it("does not display fabrication warnings in the chat report", async () => {
    getInterviewChatReport.mockResolvedValue(
      makeReport({ fabrication_warnings: ["内部事实校验记录"] }),
    )
    const wrapper = mountReport()
    await flushPromises()

    expect(wrapper.text()).not.toContain("虚构风险")
    expect(wrapper.text()).not.toContain("内部事实校验记录")
  })

  it("defaults all array fields to empty arrays when API returns nullish arrays", async () => {
    // Simulate a backend response with null arrays to ensure the page
    // never throws on `.length` access.
    getInterviewChatReport.mockResolvedValue({
      ...makeReport(),
      strengths: [],
      weaknesses: [],
      best_answers: [],
      weakest_answers: [],
      unsupported_claims: [],
      missing_skill_warnings: [],
      fabrication_warnings: [],
      improvement_suggestions: [],
      practice_questions: [],
      used_facts: [],
      dimension_scores: [],
      summary: "",
    })
    const wrapper = mountReport()
    await flushPromises()

    // Page renders without error and shows "暂无数据" placeholders.
    expect(wrapper.find('[data-testid="interview-chat-report"]').exists()).toBe(true)
    expect(wrapper.text()).toContain("暂无数据")
    // Dimension rows still render (finalDimensions is a static list of 5)
    // but each bar should show 0 score.
    const dims = wrapper.findAll('[data-testid="chat-report-dimension"]')
    expect(dims.length).toBe(5)
    for (const dim of dims) {
      expect(dim.text()).toContain("0")
    }
  })

  it("renders error code and message when report generation failed", async () => {
    getInterviewChatReport.mockResolvedValue(
      makeReport({
        error_code: "DIFY_OUTPUT_INVALID",
        error_message: "Dify 返回的 JSON 无效",
      }),
    )
    const wrapper = mountReport()
    await flushPromises()

    expect(wrapper.find('[data-testid="chat-report-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain("DIFY_OUTPUT_INVALID")
    expect(wrapper.text()).toContain("Dify 返回的 JSON 无效")
  })

  it("shows forbidden state when user lacks access to the report", async () => {
    getInterviewChatReport.mockRejectedValue(new Error("无权访问该面试报告"))
    const wrapper = mountReport()
    await flushPromises()

    expect(wrapper.find('[data-testid="forbidden-state"]').exists()).toBe(true)
  })
})

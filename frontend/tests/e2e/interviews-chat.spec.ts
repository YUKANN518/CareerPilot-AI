import { expect, test, type Page } from "@playwright/test"

import { showComplianceSnapshots } from "./support/jobs"

const CHAT_EMAIL = "match.e2e@example.com"
const CHAT_PASSWORD = "MatchPassword123!"
const BACKEND_URL = "http://127.0.0.1:8000"

const REQUIRED_CHAT_ROUTES = [
  "/api/interviews",
  "/api/interviews/{interview_id}",
  "/api/interviews/{interview_id}/chat/start",
  "/api/interviews/{interview_id}/messages",
  "/api/interviews/{interview_id}/chat/complete",
  "/api/interviews/{interview_id}/chat/cancel",
  "/api/interviews/{interview_id}/chat/status",
  "/api/interviews/{interview_id}/chat/report",
]

async function login(page: Page): Promise<void> {
  await page.goto("/auth/login")
  await page.locator('input[type="email"]').fill(CHAT_EMAIL)
  await page.locator('input[type="password"]').fill(CHAT_PASSWORD)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function openSeededJob(page: Page): Promise<void> {
  await page.goto("/jobs")
  await showComplianceSnapshots(page)
  const search = page.locator(
    'input[type="search"], input[placeholder*="搜索"]',
  ).first()
  await search.fill("Seeded Backend Engineer")
  await page
    .locator("form")
    .filter({ has: search })
    .locator('button[type="submit"]')
    .click()
  await page.getByRole("link", { name: "Seeded Backend Engineer" }).first().click()
  await expect(
    page.getByRole("heading", { name: "Seeded Backend Engineer" }),
  ).toBeVisible()
}

async function startDeterministicMatch(page: Page): Promise<void> {
  const jobMatchSelect = page.locator("#job-match-version")
  await jobMatchSelect.selectOption({ index: 0 })
  await jobMatchSelect
    .locator("xpath=ancestor::div[contains(@class,'sm:items-end')][1]/button")
    .click()
  await expect(page).toHaveURL(/\/matches\/new/)
  await page.locator("#match-resume-version").selectOption({ index: 0 })
  await page.locator('form button[type="submit"]').click()
  await expect(page).toHaveURL(/\/match-runs\/\d+\/processing/)
  await expect(page.getByRole("heading", { name: "实时匹配流程" })).toBeVisible()
}

async function waitForMatchCompletionAndOpenReport(page: Page): Promise<void> {
  await expect(page.getByTestId("node-load_inputs")).toContainText("SUCCEEDED")
  await expect(page.getByTestId("node-deterministic_matching")).toContainText("SUCCEEDED")
  await expect(page.getByTestId("node-save_report")).toContainText("SUCCEEDED")
  await page.getByRole("button", { name: "确认并打开报告" }).click()
  await expect(page).toHaveURL(/\/matches\/\d+$/)
}

async function generateInterviewAndGetId(page: Page): Promise<number> {
  const interviewId = await page.evaluate(async () => {
    const reportId = Number(window.location.pathname.split("/").at(-1))
    const tokenValue = window.localStorage.getItem("careerpilot.tokens")
    if (!tokenValue || !Number.isInteger(reportId)) {
      throw new Error("Missing authenticated match-report context")
    }
    const token = (JSON.parse(tokenValue) as { access_token: string }).access_token
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    const reportResponse = await fetch(`http://127.0.0.1:8000/api/matches/${reportId}`, {
      headers,
    })
    const reportBody = (await reportResponse.json()) as {
      data: { resume_version_id: number; job_id: number }
    }
    const response = await fetch("http://127.0.0.1:8000/api/interviews", {
      method: "POST",
      headers,
      body: JSON.stringify({
        resume_version_id: reportBody.data.resume_version_id,
        job_id: reportBody.data.job_id,
        match_report_id: reportId,
        interview_type: "TECHNICAL",
      }),
    })
    if (!response.ok) throw new Error(`Interview creation failed: ${response.status}`)
    const body = (await response.json()) as { data: { id: number } }
    return body.data.id
  })
  await page.goto(`/interviews/${interviewId}/chat`)
  return interviewId
}

const LONG_ANSWER =
  "I have used Python for three years, including building async HTTP services with asyncio " +
  "and multiprocessing workers for CPU-bound tasks in production environments."

const SHORT_ANSWER = "I know Python."

test.beforeAll(async () => {
  const response = await fetch(`${BACKEND_URL}/openapi.json`)
  if (!response.ok) {
    throw new Error(
      `Cannot fetch /openapi.json from backend: HTTP ${response.status}. ` +
        "Ensure the backend is running on 127.0.0.1:8000.",
    )
  }
  const spec = (await response.json()) as { paths?: Record<string, unknown> }
  const actualRoutes = Object.keys(spec.paths ?? {})
  const missing = REQUIRED_CHAT_ROUTES.filter(
    (route) => !actualRoutes.includes(route),
  )
  if (missing.length > 0) {
    const formatted = actualRoutes.join("\n  ")
    throw new Error(
      `Missing required chat interview routes: ${missing.join(", ")}\n` +
        `Actual OpenAPI routes:\n  ${formatted}`,
    )
  }
})

test("interview chat happy path: create, chat, follow-up, next question, complete, report", async ({
  page,
}) => {
  await login(page)
  await openSeededJob(page)
  await startDeterministicMatch(page)
  await waitForMatchCompletionAndOpenReport(page)

  // Create the hidden optional interview through its authenticated API.
  const interviewId = await generateInterviewAndGetId(page)

  // Navigate to the chat page. The page auto-starts on mount when
  // chat_status is CREATED, which calls POST /chat/start and displays
  // the first question via the FakeInterviewChatProvider.
  await page.goto(`/interviews/${interviewId}/chat`)
  await expect(page.getByTestId("interview-chat")).toBeVisible({ timeout: 15_000 })

  // The first assistant message (Q1) must appear.
  await expect(page.getByTestId("chat-message-assistant").first()).toBeVisible({
    timeout: 15_000,
  })

  // Progress shows 1/4 (FakeInterviewPlanProvider produces 4 questions).
  await expect(page.getByTestId("chat-progress")).toContainText("1/")

  // Send a short answer → Fake provider returns FOLLOW_UP.
  await page.getByTestId("chat-input").fill(SHORT_ANSWER)
  await page.getByTestId("chat-send-button").click()
  await expect(page.getByTestId("chat-message-user").first()).toBeVisible()
  // After FOLLOW_UP, progress shows 追问 1.
  await expect(page.getByTestId("chat-progress")).toContainText("追问 1", {
    timeout: 10_000,
  })

  // Send a long answer → Fake provider returns NEXT_QUESTION (Q1 → Q2).
  await page.getByTestId("chat-input").fill(LONG_ANSWER)
  await page.getByTestId("chat-send-button").click()
  await expect(page.getByTestId("chat-progress")).toContainText("2/", {
    timeout: 10_000,
  })

  // Send a long answer → NEXT_QUESTION (Q2 → Q3).
  await page.getByTestId("chat-input").fill(LONG_ANSWER)
  await page.getByTestId("chat-send-button").click()
  await expect(page.getByTestId("chat-progress")).toContainText("3/", {
    timeout: 10_000,
  })

  // Send a long answer → NEXT_QUESTION (Q3 → Q4).
  await page.getByTestId("chat-input").fill(LONG_ANSWER)
  await page.getByTestId("chat-send-button").click()
  await expect(page.getByTestId("chat-progress")).toContainText("4/", {
    timeout: 10_000,
  })

  // Send a long answer → COMPLETE_INTERVIEW.
  await page.getByTestId("chat-input").fill(LONG_ANSWER)
  await page.getByTestId("chat-send-button").click()

  // The completion banner must appear, then the page redirects to the
  // chat report page.
  await expect(page.getByTestId("chat-completion-banner")).toBeVisible({
    timeout: 10_000,
  })
  await expect(page).toHaveURL(/\/interviews\/\d+\/chat\/report$/, {
    timeout: 15_000,
  })

  // The report must render all major sections.
  await expect(page.getByTestId("interview-chat-report")).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByTestId("chat-report-overall-score")).toBeVisible()
  await expect(page.getByTestId("chat-report-dimensions")).toBeVisible()
  const dimensions = page.getByTestId("chat-report-dimension")
  await expect(dimensions.first()).toBeVisible()
  expect(await dimensions.count()).toBe(5)
  await expect(page.getByTestId("chat-report-strengths")).toBeVisible()
  await expect(page.getByTestId("chat-report-weaknesses")).toBeVisible()
  await expect(page.getByTestId("chat-report-best-answers")).toBeVisible()
  await expect(page.getByTestId("chat-report-weakest-answers")).toBeVisible()
  await expect(page.getByTestId("chat-report-fact-check")).toBeVisible()
})

test("interview chat session persists after refresh", async ({ page }) => {
  await login(page)
  await openSeededJob(page)
  await startDeterministicMatch(page)
  await waitForMatchCompletionAndOpenReport(page)

  const interviewId = await generateInterviewAndGetId(page)
  await page.goto(`/interviews/${interviewId}/chat`)
  await expect(page.getByTestId("interview-chat")).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId("chat-message-assistant").first()).toBeVisible({
    timeout: 15_000,
  })

  // Send one answer to create some chat history.
  await page.getByTestId("chat-input").fill(LONG_ANSWER)
  await page.getByTestId("chat-send-button").click()
  await expect(page.getByTestId("chat-message-user").first()).toBeVisible({
    timeout: 10_000,
  })

  // Refresh the page. The chat page must reload existing messages
  // (session resume) and not restart the interview.
  await page.reload()
  await expect(page.getByTestId("interview-chat")).toBeVisible({ timeout: 15_000 })
  // Existing messages must reappear.
  await expect(page.getByTestId("chat-message-assistant").first()).toBeVisible({
    timeout: 10_000,
  })
  await expect(page.getByTestId("chat-message-user").first()).toBeVisible()

  // Navigate to the report page URL directly. Even though the
  // interview is not yet complete, the report endpoint must respond
  // (it may show an error or a partial report, but must not 500).
  // After completing the interview via the chat-complete-button,
  // the report must be fully visible.
  // Register before clicking: window.confirm blocks the click handler until
  // Playwright accepts the dialog.
  page.once("dialog", (dialog) => dialog.accept())
  await page.getByTestId("chat-complete-button").click()
  await expect(page).toHaveURL(/\/interviews\/\d+\/chat\/report$/, {
    timeout: 15_000,
  })
  await expect(page.getByTestId("interview-chat-report")).toBeVisible({
    timeout: 15_000,
  })

  // Refresh the report page. The report must still be visible.
  await page.reload()
  await expect(page.getByTestId("interview-chat-report")).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByTestId("chat-report-overall-score")).toBeVisible()
})

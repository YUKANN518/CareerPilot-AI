import { resolve } from "node:path"

import { expect, test, type Page } from "@playwright/test"

const MATCH_EMAIL = "match.e2e@example.com"
const MATCH_PASSWORD = "MatchPassword123!"
const BACKEND_URL = "http://127.0.0.1:8000"

const REQUIRED_CAREER_ASSISTANT_ROUTES = [
  "/api/career-assistant/qa",
  "/api/career-assistant/qa/{run_id}",
  "/api/career-assistant/qa/{run_id}/event-ticket",
  "/api/career-assistant/qa/{run_id}/events",
  "/api/admin/knowledge-documents",
  "/api/admin/knowledge-documents/{document_id}",
  "/api/admin/knowledge-documents/{document_id}/reindex",
]

async function login(page: Page): Promise<void> {
  await page.goto("/auth/login")
  await page.locator('input[type="email"]').fill(MATCH_EMAIL)
  await page.locator('input[type="password"]').fill(MATCH_PASSWORD)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

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
  const missing = REQUIRED_CAREER_ASSISTANT_ROUTES.filter(
    (route) => !actualRoutes.includes(route),
  )
  if (missing.length > 0) {
    const formatted = actualRoutes.join("\n  ")
    throw new Error(
      `Missing required career-assistant routes: ${missing.join(", ")}\n` +
        `Actual OpenAPI routes:\n  ${formatted}`,
    )
  }
})

test("career assistant QA streams a knowledge-base answer without exposing citations", async ({
  page,
}) => {
  await login(page)

  await page.getByRole("link", { name: "AI 职业助手" }).click()
  await expect(page).toHaveURL(/\/career-assistant$/)
  await expect(page.getByRole("heading", { name: "AI 职业助手" })).toBeVisible()

  await page
    .getByTestId("career-question-input")
    .fill("What backend engineer experience does the candidate have?")
  await page.getByRole("button", { name: "提问" }).click()

  const activeRun = page.getByTestId("career-qa-active-run")
  await expect(activeRun).toBeVisible()
  await expect(activeRun.getByText(/PENDING|RUNNING/)).toBeVisible()

  await expect(activeRun.getByText("SUCCEEDED", { exact: true })).toBeVisible({
    timeout: 30_000,
  })
  await expect(activeRun.getByTestId("career-qa-citation-1")).toHaveCount(0)
})

test("career assistant QA scope=personal answers from user data", async ({
  page,
}) => {
  await login(page)

  await page.getByRole("link", { name: "AI 职业助手" }).click()
  await expect(page).toHaveURL(/\/career-assistant$/)

  // Select scope=personal (仅个人数据)
  await page.getByTestId("career-scope-select").selectOption("personal")

  await page
    .getByTestId("career-question-input")
    .fill("What skills do I have in my resume?")
  await page.getByRole("button", { name: "提问" }).click()

  const activeRun = page.getByTestId("career-qa-active-run")
  await expect(activeRun).toBeVisible()
  await expect(activeRun.getByText(/PENDING|RUNNING/)).toBeVisible()

  // scope=personal must complete (either with answer or insufficient evidence)
  await expect(activeRun.getByText("SUCCEEDED", { exact: true })).toBeVisible({
    timeout: 30_000,
  })
})

test("admin uploads, reindexes, and deletes a knowledge document", async ({
  page,
}) => {
  // Use sample_resume.docx (not .pdf) to avoid SHA256 collision with the
  // seeded knowledge document which already uses sample_resume.pdf.
  const sampleDocx = resolve(
    process.cwd(),
    "..",
    "backend",
    "tests",
    "fixtures",
    "sample_resume.docx",
  )
  const title = `E2E Knowledge ${Date.now()}`

  await page.goto("/auth/login")
  await page.getByLabel("邮箱").fill("admin.e2e@example.com")
  await page.getByLabel("密码").fill("AdminPassword123!")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)

  await page.getByRole("link", { name: "知识库管理" }).click()
  await expect(page).toHaveURL(/\/admin\/knowledge-documents$/)
  await expect(page.getByRole("heading", { name: "知识库管理" })).toBeVisible()

  // Seeded document must be present.
  await expect(page.getByText("E2E Career Knowledge Guide")).toBeVisible()

  // Upload a new document.
  await page.getByTestId("knowledge-title-input").fill(title)
  await page.getByTestId("knowledge-category-input").fill("e2e")
  await page.getByTestId("resume-file").setInputFiles(sampleDocx)
  await page.getByTestId("knowledge-upload-submit").click()

  await expect(page.getByRole("heading", { name: title })).toBeVisible({
    timeout: 30_000,
  })
  const newDocRow = page
    .getByRole("listitem")
    .filter({ hasText: title })
  await expect(newDocRow.getByText("已索引", { exact: true })).toBeVisible()

  // Reindex the new document.
  const reindexButton = newDocRow.getByTestId(
    new RegExp(`knowledge-document-reindex-\\d+`),
  )
  await reindexButton.click()
  await expect(page.getByText("已开始重新索引：" + title)).toBeVisible()

  // Delete the new document.
  const deleteButton = newDocRow.getByTestId(
    new RegExp(`knowledge-document-delete-\\d+`),
  )
  await deleteButton.click()
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认删除" })
    .click()
  await expect(page.getByRole("heading", { name: title })).toHaveCount(0)
})

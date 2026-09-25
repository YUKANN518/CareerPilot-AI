import { expect, test, type Page } from "@playwright/test"

import { showComplianceSnapshots } from "./support/jobs"

const MATCH_EMAIL = "match.e2e@example.com"
const MATCH_PASSWORD = "MatchPassword123!"

async function login(page: Page): Promise<void> {
  await page.goto("/auth/login")
  await page.locator('input[type="email"]').fill(MATCH_EMAIL)
  await page.locator('input[type="password"]').fill(MATCH_PASSWORD)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function openSeededJob(page: Page): Promise<void> {
  await page.goto("/jobs")
  await showComplianceSnapshots(page)
  const search = page.locator('input[type="search"], input[placeholder*="搜索"]').first()
  await search.fill("Seeded Backend Engineer")
  await page.locator("form").filter({ has: search }).locator('button[type="submit"]').click()
  await page.getByRole("link", { name: "Seeded Backend Engineer" }).first().click()
  await expect(page.getByRole("heading", { name: "Seeded Backend Engineer" })).toBeVisible()
}

async function startRun(page: Page, hybrid = false): Promise<void> {
  const jobMatchSelect = page.locator("#job-match-version")
  await jobMatchSelect.selectOption({ index: 0 })
  await jobMatchSelect
    .locator("xpath=ancestor::div[contains(@class,'sm:items-end')][1]/button")
    .click()
  await expect(page).toHaveURL(/\/matches\/new/)
  await page.locator("#match-resume-version").selectOption({ index: 0 })
  if (hybrid) await page.locator('input[value="hybrid-v1"]').check()
  await page.locator('form button[type="submit"]').click()
  await expect(page).toHaveURL(/\/match-runs\/\d+\/processing/)
  await expect(page.getByRole("heading", { name: "实时匹配流程" })).toBeVisible()
}

test("LangGraph SSE matching pauses for review and opens the real report", async ({ page }) => {
  await login(page)
  await openSeededJob(page)
  await startRun(page)

  await expect(page.getByTestId("node-load_inputs")).toContainText("已完成")
  await expect(page.getByTestId("node-deterministic_matching")).toContainText("已完成")
  await expect(page.getByTestId("node-semantic_retrieval")).toContainText("已跳过")
  await expect(page.getByTestId("node-save_report")).toContainText("已完成")
  await expect(page.getByRole("button", { name: "确认并打开报告" })).toBeVisible()
  await page.getByRole("button", { name: "确认并打开报告" }).click()

  await expect(page).toHaveURL(/\/matches\/\d+$/)
  await expect(page.getByTestId("scoring-version")).toHaveText("deterministic-v1.1")
})

test("hybrid workflow executes semantic retrieval before human confirmation", async ({
  page,
}) => {
  await login(page)
  await openSeededJob(page)
  await startRun(page, true)

  await expect(page.getByTestId("node-semantic_retrieval")).toContainText("已完成")
  await expect(page.getByRole("button", { name: "确认并打开报告" })).toBeVisible()
  await page.getByRole("button", { name: "确认并打开报告" }).click()
  await expect(page).toHaveURL(/\/matches\/\d+$/)
  await expect(page.getByTestId("scoring-version")).toHaveText("hybrid-v1")
  await expect(page.getByTestId("semantic-evidence-section")).toBeVisible()
})

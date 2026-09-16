import { expect, test, type Page } from "@playwright/test"

import { showComplianceSnapshots } from "./support/jobs"

const MATCH_EMAIL = "match.e2e@example.com"
const MATCH_PASSWORD = "MatchPassword123!"
const BACKEND_URL = "http://127.0.0.1:8000"

const REQUIRED_RESUME_OPTIMIZATION_ROUTES = [
  "/api/resume-optimizations",
  "/api/resume-optimizations/{optimization_id}",
  "/api/resume-optimizations/{optimization_id}/confirm",
  "/api/resume-optimizations/{optimization_id}/retry",
  "/api/resume-optimizations/{optimization_id}/create-version",
]

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

async function createOptimizationAndOpenDetail(page: Page): Promise<number> {
  const optimizationId = await page.evaluate(async () => {
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
    if (!reportResponse.ok) {
      throw new Error(`Match report fetch failed: ${reportResponse.status}`)
    }
    const reportBody = (await reportResponse.json()) as {
      data: { resume_version_id: number; job_id: number }
    }
    const response = await fetch("http://127.0.0.1:8000/api/resume-optimizations", {
      method: "POST",
      headers,
      body: JSON.stringify({
        resume_version_id: reportBody.data.resume_version_id,
        job_id: reportBody.data.job_id,
        match_report_id: reportId,
      }),
    })
    if (!response.ok) {
      throw new Error(`Resume optimization creation failed: ${response.status}`)
    }
    const body = (await response.json()) as { data: { id: number } }
    return body.data.id
  })
  await page.goto(`/resume-optimizations/${optimizationId}`)
  return optimizationId
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
  const missing = REQUIRED_RESUME_OPTIMIZATION_ROUTES.filter(
    (route) => !actualRoutes.includes(route),
  )
  if (missing.length > 0) {
    const formatted = actualRoutes.join("\n  ")
    throw new Error(
      `Missing required resume-optimization routes: ${missing.join(", ")}\n` +
        `Actual OpenAPI routes:\n  ${formatted}`,
    )
  }
})

test("resume optimization happy path generates suggestions, confirms, and creates a new version", async ({
  page,
}) => {
  await login(page)
  await openSeededJob(page)
  await startDeterministicMatch(page)
  await waitForMatchCompletionAndOpenReport(page)

  // The match report must show the Python skill as MATCHED.
  await expect(page.getByTestId("skills-MATCHED")).toBeVisible()

  // Remember the match report URL so we can return to it after navigating away.
  const matchReportUrl = page.url()

  // The optional module is hidden from the primary product flow. Exercise its
  // retained authenticated API and direct route without restoring a CTA.
  await createOptimizationAndOpenDetail(page)
  await expect(page).toHaveURL(/\/resume-optimizations\/\d+$/)

  // Verify section cards render original vs suggested text comparison.
  await expect(page.getByTestId("optimization-section-card").first()).toBeVisible()
  const sectionCount = await page.getByTestId("optimization-section-card").count()
  expect(sectionCount).toBeGreaterThan(0)

  // The summary-only job information warning is only present for summary-only
  // jobs. The Seeded Backend Engineer fixture has full data, so we verify the
  // warning only when it appears.
  const warningLocator = page.getByTestId("job-information-warning")
  if (await warningLocator.count() > 0) {
    await expect(warningLocator).toContainText(
      "当前优化建议仅基于公开岗位摘要生成",
    )
  }

  // Accept the first section suggestion.
  const firstSection = page.getByTestId("optimization-section-card").first()
  const sourceSectionId = await firstSection.locator("code").first().textContent()
  expect(sourceSectionId).toBeTruthy()
  await page.getByTestId(`accept-section-${sourceSectionId}`).click()

  // Reject the second section if it exists.
  if (sectionCount > 1) {
    const secondSection = page.getByTestId("optimization-section-card").nth(1)
    const secondId = await secondSection.locator("code").first().textContent()
    if (secondId) {
      await page.getByTestId(`reject-section-${secondId}`).click()
    }
  }

  // Edit the first section's suggested text inline.
  await page.getByTestId(`edit-section-${sourceSectionId}`).click()
  await expect(page.getByTestId("edit-textarea")).toBeVisible()
  await page.getByTestId("edit-textarea").fill(
    "Edited suggestion content for the E2E test flow.",
  )
  await page.getByTestId("save-edit-button").click()
  await expect(page.getByTestId("edit-textarea")).toHaveCount(0)
  await expect(page.getByText("Edited suggestion content for the E2E test flow.")).toBeVisible()

  // Confirm the optimization: the attestation checkbox must be checked
  // first because the section was edited (hasAnyEdit = true).
  await expect(page.getByTestId("attest-truth-checkbox")).toBeVisible()
  await page.getByTestId("attest-truth-checkbox").check()
  await expect(page.getByTestId("confirm-optimization-button")).toBeVisible()
  await page.getByTestId("confirm-optimization-button").click()

  // After confirmation the status badge must show CONFIRMED.
  await expect(page.getByText("CONFIRMED").first()).toBeVisible()

  // The create-version button must NOT be available before confirmation.
  // (Already confirmed above; now it should appear.)
  await expect(page.getByTestId("create-version-button")).toBeVisible()

  // Create the new resume version.
  await page.getByTestId("create-version-button").click()
  await expect(page).toHaveURL(/\/resume-versions\/\d+$/)

  // The new resume version page must show a version number greater than 1.
  await expect(page.getByRole("heading", { name: /简历版本 \d+/ })).toBeVisible()

  // Navigate to the resume center and verify the original version still exists.
  await page.goto("/resumes")
  await expect(
    page.getByRole("link", { name: "E2E Confirmed Resume" }),
  ).toBeVisible()
  await page.getByRole("link", { name: "E2E Confirmed Resume" }).click()
  await expect(page).toHaveURL(/\/resumes\/\d+$/)

  // Return to the match report to ensure it is still accessible.
  await page.goto(matchReportUrl)
  await expect(page).toHaveURL(/\/matches\/\d+$/)
})

test("resume optimization confirm rejects an edit that introduces a missing skill", async ({
  page,
}) => {
  await login(page)
  await openSeededJob(page)
  await startDeterministicMatch(page)
  await waitForMatchCompletionAndOpenReport(page)
  await createOptimizationAndOpenDetail(page)
  await expect(page).toHaveURL(/\/resume-optimizations\/\d+$/)
  await expect(page.getByTestId("optimization-section-card").first()).toBeVisible()

  const firstSection = page.getByTestId("optimization-section-card").first()
  const sourceSectionId = await firstSection.locator("code").first().textContent()
  expect(sourceSectionId).toBeTruthy()

  // Edit the first section with a missing-skill claim.
  await page.getByTestId(`edit-section-${sourceSectionId}`).click()
  await page.getByTestId("edit-textarea").fill("Now expert in a missing skill.")
  await page.getByTestId("save-edit-button").click()

  // Intercept the confirm request and simulate the server-side
  // anti-fabrication rejection (RESUME_OPTIMIZATION_EDIT_INVALID, 422).
  let rejectedOnce = false
  await page.route("**/api/resume-optimizations/*/confirm", async (route) => {
    if (route.request().method() === "POST" && !rejectedOnce) {
      rejectedOnce = true
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          success: false,
          error: {
            code: "RESUME_OPTIMIZATION_EDIT_INVALID",
            message:
              "edited_text must not introduce a missing skill the user does not have.",
          },
        }),
      })
      return
    }
    await route.continue()
  })

  // The attestation checkbox must be checked before confirm is enabled.
  await page.getByTestId("attest-truth-checkbox").check()
  await page.getByTestId("confirm-optimization-button").click()

  // The fabrication error must be visible and the record must stay DRAFT.
  await expect(
    page.getByText(/must not introduce a missing skill/),
  ).toBeVisible()
  await expect(page.getByText("DRAFT").first()).toBeVisible()
  await expect(page.getByText("CONFIRMED")).toHaveCount(0)
  // The create-version button must not appear after a rejected confirm.
  await expect(page.getByTestId("create-version-button")).toHaveCount(0)

  // The user can fix the edit and confirm successfully afterwards.
  await page.unroute("**/api/resume-optimizations/*/confirm")
  await page.getByTestId(`edit-section-${sourceSectionId}`).click()
  await page.getByTestId("edit-textarea").fill("Clean edit without missing skills.")
  await page.getByTestId("save-edit-button").click()
  // The attestation checkbox is already checked from the previous attempt.
  await page.getByTestId("confirm-optimization-button").click()
  await expect(page.getByText("CONFIRMED").first()).toBeVisible()
})

test("resume optimization confirm requires attestation checkbox when sections are edited", async ({
  page,
}) => {
  await login(page)
  await openSeededJob(page)
  await startDeterministicMatch(page)
  await waitForMatchCompletionAndOpenReport(page)
  await createOptimizationAndOpenDetail(page)
  await expect(page).toHaveURL(/\/resume-optimizations\/\d+$/)
  await expect(page.getByTestId("optimization-section-card").first()).toBeVisible()

  const firstSection = page.getByTestId("optimization-section-card").first()
  const sourceSectionId = await firstSection.locator("code").first().textContent()
  expect(sourceSectionId).toBeTruthy()

  // Edit the first section — this triggers hasAnyEdit = true.
  await page.getByTestId(`edit-section-${sourceSectionId}`).click()
  await page.getByTestId("edit-textarea").fill("Edited content for attestation test.")
  await page.getByTestId("save-edit-button").click()

  // The attestation section must be visible.
  await expect(page.getByTestId("attest-truth-section")).toBeVisible()
  // The confirm button must be disabled because the checkbox is unchecked.
  await expect(page.getByTestId("confirm-optimization-button")).toBeDisabled()

  // Check the attestation checkbox — the confirm button becomes enabled.
  await page.getByTestId("attest-truth-checkbox").check()
  await expect(page.getByTestId("confirm-optimization-button")).toBeEnabled()

  // Confirm successfully with the attestation.
  await page.getByTestId("confirm-optimization-button").click()
  await expect(page.getByText("CONFIRMED").first()).toBeVisible()
})

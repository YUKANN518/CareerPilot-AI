import { expect, test, type Page } from "@playwright/test"

const EMAIL = "match.e2e@example.com"
const PASSWORD = "MatchPassword123!"

async function login(page: Page): Promise<void> {
  await page.goto("/auth/login")
  await page.getByLabel("邮箱").fill(EMAIL)
  await page.getByLabel("密码").fill(PASSWORD)
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

test("portfolio main flow: confirmed resume to evidence-grounded match report", async ({
  page,
}) => {
  await login(page)

  await page.getByRole("link", { name: "简历", exact: true }).click()
  const resumeRow = page.getByRole("row").filter({ hasText: "E2E Confirmed Resume" })
  await expect(resumeRow.getByText("已确认", { exact: true })).toBeVisible()
  await resumeRow.getByRole("link", { name: "E2E Confirmed Resume" }).click()
  await expect(page).toHaveURL(/\/resumes\/\d+$/)

  await page.getByRole("link", { name: "岗位", exact: true }).click()
  const search = page.locator('input[placeholder="搜索职位、公司或岗位描述"]')
  await search.fill("Skill Gap Engineer")
  await page.locator("form").filter({ has: search }).getByRole("button").click()
  await page.getByRole("link", { name: "Skill Gap Engineer" }).first().click()

  await page.locator("#job-match-version").selectOption({ index: 0 })
  await page
    .locator("#job-match-version")
    .locator("xpath=ancestor::div[contains(@class,'sm:items-end')][1]/button")
    .click()
  await page.locator("#match-resume-version").selectOption({ index: 0 })
  await page.locator('input[value="hybrid-v1"]').check()
  await page.locator('form button[type="submit"]').click()

  await expect(page.getByTestId("node-load_inputs")).toContainText("SUCCEEDED")
  await expect(page.getByTestId("node-deterministic_matching")).toContainText("SUCCEEDED")
  await expect(page.getByTestId("node-semantic_retrieval")).toContainText("SUCCEEDED")
  await expect(page.getByTestId("node-save_report")).toContainText("SUCCEEDED")
  await page.getByRole("button", { name: "确认并打开报告" }).click()

  await expect(page).toHaveURL(/\/matches\/\d+$/)
  await expect(page.getByText("/100", { exact: true })).toBeVisible()
  await expect(page.getByTestId("skills-MATCHED")).toContainText("Python")
  await expect(page.getByTestId("skill-evidence-Python")).toBeVisible()
  await expect(page.getByTestId("skills-MISSING")).toContainText("Docker")
  await expect(page.getByTestId("skills-MISSING")).toContainText("未找到已确认的证据")
  await expect(page.getByTestId("evidence-coverage")).toBeVisible()
  await expect(page.getByTestId("semantic-evidence-section")).toBeVisible()
  await expect(page.getByTestId("blocking-risk-section")).toBeVisible()
  await expect(page.getByRole("heading", { name: "阻断风险" })).toBeVisible()
})

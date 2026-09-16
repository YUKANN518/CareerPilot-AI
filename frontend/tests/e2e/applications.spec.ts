import { expect, test } from "@playwright/test"

import { showComplianceSnapshots } from "./support/jobs"

test("user adds a job to the application board and persists status transitions", async ({ page }) => {
  const email = `applications-e2e-${Date.now()}@example.com`

  await page.goto("/auth/register")
  await page.getByLabel("姓名").fill("Applications E2E User")
  await page.getByLabel("邮箱").fill(email)
  await page.getByLabel("密码").fill("StrongPassword123!")
  await page.getByRole("button", { name: "注册", exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)

  await page.goto("/jobs")
  await showComplianceSnapshots(page)
  await page.getByRole("link", { name: "Seeded Backend Engineer" }).first().click()
  await expect(page.getByRole("heading", { name: "Seeded Backend Engineer" })).toBeVisible()
  await page.getByRole("button", { name: "加入投递管理" }).click()

  await expect(page).toHaveURL(/\/applications$/)
  const applicationCard = page.locator('[draggable="true"]').filter({ hasText: "Seeded Backend Engineer" })
  await expect(applicationCard).toBeVisible()
  await applicationCard.dragTo(page.getByTestId("application-column-APPLIED"))
  await expect(page.getByTestId("application-column-APPLIED")).toContainText(
    "Seeded Backend Engineer",
  )
  const appliedCard = page.locator('[draggable="true"]').filter({ hasText: "Seeded Backend Engineer" })
  await appliedCard.scrollIntoViewIfNeeded()
  await appliedCard.click()
  await page.getByLabel("当前投递状态").selectOption("INTERVIEW")
  await page.getByRole("button", { name: "更新状态" }).click()
  await page.getByRole("button", { name: "关闭" }).click()
  await expect(page.getByTestId("application-column-INTERVIEW")).toContainText(
    "Seeded Backend Engineer",
  )
})

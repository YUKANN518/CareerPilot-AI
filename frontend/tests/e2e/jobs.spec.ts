import { expect, test } from "@playwright/test"

import { showComplianceSnapshots } from "./support/jobs"

test("ordinary user searches, filters, opens a real job, and cannot enter admin", async ({
  page,
}) => {
  const email = `jobs-e2e-${Date.now()}@example.com`

  await page.goto("/auth/register")
  await page.getByLabel("姓名").fill("Jobs E2E User")
  await page.getByLabel("邮箱").fill(email)
  await page.getByLabel("密码").fill("StrongPassword123!")
  await page.getByRole("button", { name: "注册", exact: true }).click()

  await page.getByRole("link", { name: "岗位", exact: true }).click()
  await expect(page.getByRole("heading", { name: "岗位", exact: true })).toBeVisible()
  await showComplianceSnapshots(page)
  await expect(page.getByText("Seeded Backend Engineer")).toBeVisible()

  await page
    .getByPlaceholder("搜索职位、公司或岗位描述")
    .fill("Seeded Backend")
  await page.getByLabel("地点").fill("Shanghai")
  await page.getByLabel("工作类型").selectOption("FULL_TIME")
  await page.getByLabel("经验要求").selectOption("MID")
  await page.getByRole("button", { name: "应用筛选" }).click()
  await expect(page.getByText("Seeded Backend Engineer")).toBeVisible()
  await expect(page.getByText("共 1 个目标岗位")).toBeVisible()

  await page.getByRole("link", { name: "Seeded Backend Engineer" }).first().click()
  await expect(page.getByRole("heading", { name: "Seeded Backend Engineer" })).toBeVisible()
  await expect(page.getByText("CareerPilot E2E", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "收藏岗位" }).click()
  await expect(page.getByRole("button", { name: "取消收藏" })).toBeVisible()

  await page.context().route("https://jobs.example.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<html><title>Local original job fixture</title></html>",
    })
  })
  const popupPromise = page.waitForEvent("popup")
  await page.getByRole("button", { name: "打开原始来源" }).click()
  const popup = await popupPromise
  await expect(popup).toHaveURL("https://jobs.example.com/seed-job-1")
  await popup.close()

  await page.goto("/jobs/favorites")
  await expect(page.getByRole("heading", { name: "我的收藏" })).toBeVisible()
  await expect(page.getByText("Seeded Backend Engineer")).toBeVisible()

  await page.goto("/admin")
  await expect(page).toHaveURL(/\/forbidden$/)
  await expect(page.getByRole("heading", { name: "没有访问权限" })).toBeVisible()
})

import { expect, test } from "@playwright/test"

test("register, logout, and login through the real API", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`
  const password = "StrongPassword123!"

  await page.goto("/auth/register")
  await page.getByLabel("姓名").fill("E2E User")
  await page.getByLabel("邮箱").fill(email)
  await page.getByLabel("密码").fill(password)
  await page.getByRole("button", { name: "注册", exact: true }).click()

  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole("heading", { name: "用户工作台" })).toBeVisible()

  await page.getByRole("button", { name: "退出登录" }).click()
  await expect(page).toHaveURL(/\/auth\/login$/)

  await page.getByLabel("邮箱").fill(email)
  await page.getByLabel("密码").fill(password)
  await page.getByRole("button", { name: "登录", exact: true }).click()

  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByText(email)).toBeVisible()
})

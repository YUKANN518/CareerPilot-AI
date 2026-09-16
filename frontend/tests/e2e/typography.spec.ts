import { mkdirSync } from "node:fs"
import { dirname, resolve } from "node:path"

import { expect, test } from "@playwright/test"

const screenshotPath = resolve(
  process.cwd(),
  "..",
  "output",
  "playwright",
  "dashboard-typography-1440x1024.png",
)

test("dashboard typography tokens remain readable at 1440px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  await page.goto("/auth/login")
  await page.locator('input[type="email"]').fill("admin.e2e@example.com")
  await page.locator('input[type="password"]').fill("AdminPassword123!")
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.locator("main h1")).toBeVisible()

  const bodyTypography = await page.locator("body").evaluate((element) => {
    const style = getComputedStyle(element)
    return { fontSize: style.fontSize, lineHeight: style.lineHeight }
  })
  expect(bodyTypography).toEqual({ fontSize: "15px", lineHeight: "24px" })

  const pageTitleTypography = await page.locator("main h1").evaluate((element) => {
    const style = getComputedStyle(element)
    return { fontSize: style.fontSize, lineHeight: style.lineHeight }
  })
  expect(pageTitleTypography).toEqual({ fontSize: "28px", lineHeight: "36px" })

  const sectionHeadingSizes = await page.locator("main h2").evaluateAll((elements) =>
    elements.map((element) => {
      const style = getComputedStyle(element)
      return `${style.fontSize}/${style.lineHeight}`
    }),
  )
  expect(sectionHeadingSizes).toContain("18px/26px")

  const navigationItem = page.locator("aside nav a").first()
  await expect(navigationItem).toHaveCSS("font-size", "15px")
  await expect(navigationItem).toHaveCSS("height", "44px")
  await expect(navigationItem.locator("svg")).toHaveCSS("width", "18px")

  await expect(page.locator("header").getByText("工作台", { exact: true })).toHaveCSS(
    "font-size",
    "14px",
  )
  await expect(page.locator("main article").first().locator("p").first()).toHaveCSS(
    "font-size",
    "14px",
  )
  await expect(page.locator("main article").first().locator("p").nth(1)).toHaveCSS(
    "font-size",
    "30px",
  )
  await expect(page.locator("main header span.inline-flex.rounded-full").first()).toHaveCSS(
    "font-size",
    "12px",
  )

  mkdirSync(dirname(screenshotPath), { recursive: true })
  await page.screenshot({ path: screenshotPath })
})

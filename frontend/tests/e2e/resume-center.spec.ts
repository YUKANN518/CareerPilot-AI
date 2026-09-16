import { resolve } from "node:path"

import { expect, test } from "@playwright/test"

test("upload, extract, parse, edit, confirm, and inspect skill evidence", async ({
  page,
}) => {
  const email = `resume-e2e-${Date.now()}@example.com`
  const sampleResume = resolve(
    process.cwd(),
    "..",
    "backend",
    "tests",
    "fixtures",
    "sample_resume.pdf",
  )

  await page.goto("/auth/register")
  await page.getByLabel("姓名").fill("Resume E2E User")
  await page.getByLabel("邮箱").fill(email)
  await page.getByLabel("密码").fill("StrongPassword123!")
  await page.getByRole("button", { name: "注册", exact: true }).click()

  await page.getByRole("link", { name: "简历", exact: true }).click()
  await page.getByRole("button", { name: "上传简历" }).click()
  await page.getByTestId("resume-file").setInputFiles(sampleResume)
  await page.getByRole("button", { name: "上传并继续" }).click()

  await expect(page).toHaveURL(/\/resumes\/\d+$/)
  await expect(page.getByText("已上传", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "提取文本" }).click()
  await expect(page.getByText("已提取", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "执行结构化解析" }).click()

  await expect(page).toHaveURL(/\/resumes\/\d+\/confirm$/)
  await expect(page.getByRole("heading", { name: "确认解析结果" })).toBeVisible()
  await page.getByLabel("姓名").click()
  await expect(page.getByTestId("active-evidence-source")).toContainText("第 1 页")
  await page.getByLabel("姓名").fill("Edited E2E Candidate")
  await page.getByRole("button", { name: "保存草稿" }).click()
  await expect(page.getByText("草稿已保存，尚未生成正式版本。")).toBeVisible()
  await page.getByRole("button", { name: "确认简历", exact: true }).click()
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认简历", exact: true })
    .click()

  await expect(page).toHaveURL(/\/resume-versions\/\d+$/)
  await expect(page.getByRole("heading", { name: "简历版本 1" })).toBeVisible()
  await expect(page.getByText("Edited E2E Candidate")).toBeVisible()
  await expect(page.getByRole("heading", { name: "技能与证据" })).toBeVisible()
  await expect(page.getByText("Python", { exact: true })).toBeVisible()
  await expect(page.getByText(/来源：page:1:block:/).first()).toBeVisible()
})

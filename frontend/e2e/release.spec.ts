import { expect, test, type Page } from "@playwright/test";

const password = process.env.PHASE14_ADMIN_PASSWORD;

if (!password) {
  throw new Error("Set PHASE14_ADMIN_PASSWORD before running the release E2E suite.");
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

async function ask(page: Page, prompt: string) {
  await page.locator("#ask-message").fill(prompt);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(prompt)).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible({ timeout: 120_000 });
  await expect(page.locator("article").last().getByRole("alert")).toHaveCount(0);
}

test.describe.serial("Phase 14 release verification", () => {
  test("login, dashboard, SKU detail, comparison, and server-side invalid comparison", async ({ page }) => {
    await login(page);
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

    await page.goto("/skus/ecoflow-delta2");
    await expect(page.getByRole("heading", { name: "EcoFlow DELTA 2" })).toBeVisible();
    await expect(page.getByText("fan is extremely loud").first()).toBeVisible();

    await page.goto("/compare");
    await expect(page.getByRole("heading", { name: "Compare SKUs" })).toBeVisible();
    await page.getByLabel("SKU A").selectOption("ecoflow-delta2");
    await expect(page.getByLabel("SKU B")).toHaveValue("jackery-explorer-1000");

    const token = await page.evaluate(() => localStorage.getItem("voc.access-token"));
    const invalid = await page.request.get("http://127.0.0.1:8014/api/compare?sku_code=ecoflow-delta2&sku_code=anker-solix-f2000&week_id=202403", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(invalid.status()).toBe(400);
    await page.getByLabel("SKU A").selectOption("anker-solix-f2000");
    await expect(page.getByLabel("SKU A")).toHaveValue("anker-solix-f2000");
    await expect(page.getByText("No comparable pair is available")).toBeVisible();
  });

  test("report generation and regeneration persist a weekly report", async ({ page }) => {
    await login(page);
    await page.goto("/reports");
    await page.getByLabel("Report SKU").selectOption("ecoflow-delta2");
    await page.getByLabel("Report week").selectOption("202403");
    await page.getByRole("button", { name: "Generate report" }).click();
    await expect(page.getByText("Weekly report available")).toBeVisible({ timeout: 120_000 });
    await page.getByRole("button", { name: "Regenerate report" }).click();
    await expect(page.getByText("Weekly report available")).toBeVisible({ timeout: 120_000 });
  });

  test("controlled Ask supports SQL, RAG, hybrid, follow-up, citations, and abstention", async ({ page }) => {
    await login(page);
    await page.goto("/ask");
    await ask(page, "Use tool_sql to count reviews and mentions for jackery-explorer-1000 in ISO week 202403.");
    await ask(page, "What noise complaints do customers report about ecoflow-delta2 in ISO week 202403? Include an exact customer example.");
    await expect(page.getByRole("button", { name: "Open citation 1" }).last()).toBeVisible();
    await page.getByRole("button", { name: "Open citation 1" }).last().click();
    await expect(page.getByRole("dialog", { name: "Citation 1" })).toContainText("fan is extremely loud");
    await ask(page, "Use tool_sql for the review count and tool_rag for an exact customer example about fan noise for ecoflow-delta2 in ISO week 202403.");
    await ask(page, "What about jackery-explorer-1000 for the same week? Use tool_sql for its review count and tool_rag for one exact customer example.");
    await ask(page, "Use tool_rag to check what evidence exists for ecoflow-delta2 in ISO week 202452.");
    await expect(page.getByText("No matching VOC data was found for this request.")).toBeVisible();
  });

  test("logout and expired authentication return to login", async ({ page }) => {
    await login(page);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await login(page);
    await page.evaluate(() => localStorage.setItem("voc.access-token", "expired-token"));
    await page.goto("/overview");
    await expect(page).toHaveURL(/\/login$/);
  });
});

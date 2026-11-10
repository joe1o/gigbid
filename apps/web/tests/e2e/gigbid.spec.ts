// gigbid.spec.ts - the 5 required end-to-end UI tests:
//   1. onboarding   2. approving a proposal   3. rejecting with a reason
//   4. editing a draft   5. the "marketplace unavailable" banner
import { expect, test, type Page } from "@playwright/test";

const REVIEWER = { email: "reviewer@gigbid.app", password: "review-local-only" };

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(REVIEWER.email);
  await page.getByLabel("Password").fill(REVIEWER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/inbox/);
}

/** Open the studio for the n-th job that is waiting for approval (scouting first if needed). */
async function openDraft(page: Page, n: number) {
  await page.goto("/inbox");
  if (await page.getByText("No jobs yet").isVisible().catch(() => false)) {
    await page.getByRole("button", { name: "Find new jobs" }).first().click();
  }
  await page.getByRole("tab", { name: /Needs approval/ }).click();
  const openLinks = page.locator("table.responsive tbody tr").getByRole("link", { name: "Open" });
  await expect(openLinks.nth(n)).toBeVisible({ timeout: 150_000 });
  await openLinks.nth(n).click();
  await expect(page.getByText("Dry-run preview")).toBeVisible();
}

test.describe.serial("GigBid", () => {
  test("1. onboarding: sign up, pick a profile, connect GigSim, set budget", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: "Create one" }).click();
    await page.getByLabel("Email").fill(`e2e-${Date.now()}@example.com`);
    await page.getByLabel(/Password/).fill("a-strong-password");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/onboarding/);

    await page.getByText("Omar Raza").click();                          // step 1: profile
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByLabel(/GigSim account/)).toHaveValue("web_developer");   // step 2: marketplace
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "Your portfolio" })).toBeVisible();   // step 3
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Weekly Connects budget").fill("80");        // step 4: rates + budget
    await page.getByLabel(/Saved search keywords/).fill("Stripe");
    await page.getByRole("button", { name: "Finish and find jobs" }).click();

    await expect(page).toHaveURL(/\/inbox/);
    await expect(page.getByRole("heading", { name: "Jobs worth a look" })).toBeVisible();
    await expect(page.locator("table.responsive tbody tr").first()).toBeVisible({ timeout: 60_000 });
  });

  test("2. approving a proposal submits it and shows live progress", async ({ page }) => {
    await signIn(page);
    await openDraft(page, 0);
    await page.getByRole("button", { name: /Approve and send/ }).click();
    await expect(page).toHaveURL(/\/runs\//);
    await expect(page.getByText("Proposal submitted")).toBeVisible();
    await expect(page.getByText("Run finished: submitted")).toBeVisible();
  });

  test("3. rejecting needs a reason and sends nothing", async ({ page }) => {
    await signIn(page);
    await openDraft(page, 0);
    const reject = page.getByRole("button", { name: "Reject", exact: true });
    await expect(reject).toBeDisabled();                                 // no reason yet
    await page.getByLabel("Reject with a reason").fill("Budget too low for this scope");
    await reject.click();
    await expect(page.getByText("Run finished: rejected")).toBeVisible();
    await expect(page.getByText("Proposal submitted")).toHaveCount(0);
  });

  test("4. editing a draft re-checks it and returns it for approval", async ({ page }) => {
    await signIn(page);
    await openDraft(page, 0);
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const first = page.getByLabel("Paragraph 1");
    await first.fill("Your team needs answers it can trust, so I would start by agreeing the success measure with you.");
    await page.getByRole("button", { name: "Save changes and re-check" }).click();
    await expect(page).toHaveURL(/\/runs\//);
    await expect(page.getByText("Your edits re-checked")).toBeVisible();
    await page.getByRole("link", { name: "Review and approve" }).click();
    await expect(page.getByText(/edited by you/)).toBeVisible();
    await expect(page.getByText("Your team needs answers it can trust")).toBeVisible();
  });

  test("5. degraded mode: banner when the marketplace is unavailable", async ({ page }) => {
    await signIn(page);
    await page.request.post("/api/test/marketplace?down=true");
    await page.goto("/inbox");
    await expect(page.getByTestId("degraded-banner")).toBeVisible();
    await expect(page.getByTestId("degraded-banner")).toContainText("Marketplace unavailable");
    await page.request.post("/api/test/marketplace?down=false");
    await page.reload();
    await expect(page.getByTestId("degraded-banner")).toHaveCount(0);
  });
});

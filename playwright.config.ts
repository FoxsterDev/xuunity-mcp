import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.XUUNITY_SITE_PORT ?? 4173);
const baseURL = process.env.XUUNITY_SITE_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/site",
  outputDir: "test-results/site-ui",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 30_000,
  expect: {
    timeout: 5_000
  },
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["json", { outputFile: "test-results/site-ui/results.json" }],
    ["junit", { outputFile: "test-results/site-ui/junit.xml" }]
  ],
  use: {
    baseURL,
    actionTimeout: 8_000,
    navigationTimeout: 15_000,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  webServer: {
    command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory docs`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe",
    timeout: 15_000
  },
  projects: [
    {
      name: "chromium-desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 980 }
      }
    },
    {
      name: "chromium-mobile",
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 390, height: 900 }
      }
    },
    {
      name: "chromium-narrow",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 320, height: 900 }
      }
    }
  ]
});

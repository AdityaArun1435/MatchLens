import os from "node:os";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// Browser tests run against the real FastAPI backend with the canned "fake" model (no Ollama needed) and a throwaway
// cache directory. If you already started `.\start.ps1 -Fake`, those servers are reused.
const root = path.resolve(__dirname, "..");
const python = process.platform === "win32" ? path.join(root, ".venv", "Scripts", "python.exe") : path.join(root, ".venv", "bin", "python");

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  webServer: [
    {
      command: `"${python}" -m uvicorn matchlens.api:app --port 8000`,
      cwd: root,
      url: "http://localhost:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: { MATCHLENS_LLM_PROVIDER: "fake", MATCHLENS_GENERATED_DIR: path.join(os.tmpdir(), `matchlens-e2e-${Date.now()}`) },
    },
    {
      command: "npm run dev -- --port 3000",
      cwd: __dirname,
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 180_000,
      env: { NEXT_PUBLIC_API_URL: "http://localhost:8000" },
    },
  ],
});

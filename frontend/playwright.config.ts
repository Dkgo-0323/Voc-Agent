import { defineConfig } from "@playwright/test";
import { liveConfiguration } from "./e2e/runtime.mjs";

const config = liveConfiguration(process.env);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3014",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      cwd: __dirname,
      env: { ...process.env, DATABASE_URL: config.databaseUrl, MILVUS_COLLECTION_NAME: config.collection },
      url: "http://127.0.0.1:8014/health",
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 3014",
      cwd: __dirname,
      env: { ...process.env, NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8014" },
      url: "http://127.0.0.1:3014/login",
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});

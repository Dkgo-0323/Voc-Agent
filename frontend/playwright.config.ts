import { defineConfig } from "@playwright/test";
import path from "node:path";

const databaseUrl = process.env.PHASE14_DATABASE_URL;
const milvusCollection = process.env.PHASE14_MILVUS_COLLECTION;

if (!databaseUrl || !milvusCollection) {
  throw new Error("Set PHASE14_DATABASE_URL and PHASE14_MILVUS_COLLECTION before running the release E2E suite.");
}

const repositoryRoot = path.resolve(__dirname, "..");

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
      command: ".\\.venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8014",
      cwd: repositoryRoot,
      env: { ...process.env, DATABASE_URL: databaseUrl, MILVUS_COLLECTION_NAME: milvusCollection },
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

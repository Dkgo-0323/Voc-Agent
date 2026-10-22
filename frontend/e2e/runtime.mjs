import { existsSync } from "node:fs";
import path from "node:path";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function liveConfiguration(env) {
  if (env.PHASE14_ALLOW_LIVE !== "1") {
    throw new Error("Release E2E calls real providers. Set PHASE14_ALLOW_LIVE=1 only after approval.");
  }
  if (!uuid.test(env.PHASE14_RUN_ID ?? "")) {
    throw new Error("Set a fresh UUID in PHASE14_RUN_ID for this acceptance run.");
  }
  let database;
  try { database = new URL(env.PHASE14_DATABASE_URL); } catch {
    throw new Error("Set PHASE14_DATABASE_URL to a disposable local PostgreSQL database.");
  }
  if (database.protocol !== "postgresql+asyncpg:" || database.search || database.hash
      || !["localhost", "127.0.0.1", "[::1]"].includes(database.hostname)
      || !/^\/(voc_phase14|voc_acceptance_[a-z0-9_]+)$/.test(database.pathname)) {
    throw new Error("Release E2E requires a local voc_phase14 or voc_acceptance_* database.");
  }
  if (!/^(aspect_mentions_phase14_[a-z0-9_]+|voc_acceptance_[a-z0-9_]+)$/.test(env.PHASE14_MILVUS_COLLECTION ?? "")) {
    throw new Error("Set a dedicated PHASE14_MILVUS_COLLECTION with a phase14/acceptance prefix.");
  }
  return { runId: env.PHASE14_RUN_ID.toLowerCase(), databaseUrl: env.PHASE14_DATABASE_URL,
    collection: env.PHASE14_MILVUS_COLLECTION };
}

export function backendPython(root, platform = process.platform, override, exists = existsSync) {
  const paths = platform === "win32" ? path.win32 : path.posix;
  if (override && !paths.isAbsolute(override)) {
    throw new Error("PHASE14_PYTHON must be an absolute interpreter path.");
  }
  const python = override || paths.join(root, ".venv", platform === "win32" ? "Scripts" : "bin",
    platform === "win32" ? "python.exe" : "python");
  if (!exists(python)) throw new Error("Acceptance Python is missing; install dependencies or set PHASE14_PYTHON.");
  return python;
}

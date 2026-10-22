// Explicit interpreter, no shell quoting and no automatic root .env loading.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { backendPython, liveConfiguration } from "./runtime.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const config = liveConfiguration(process.env);
const python = backendPython(root, process.platform, process.env.PHASE14_PYTHON);
mkdirSync(path.join(root, "dist"), { recursive: true });
const temporaryRoot = path.join(root, "dist");
const cwd = mkdtempSync(path.join(temporaryRoot, "voc-e2e-"));
function cleanup() {
  const relative = path.relative(temporaryRoot, path.resolve(cwd));
  if (!relative.startsWith("voc-e2e-") || relative.includes(path.sep) || path.isAbsolute(relative)) {
    throw new Error("Refusing to remove an unexpected acceptance directory.");
  }
  rmSync(cwd, { recursive: true, force: true });
}
const child = spawn(python, ["-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8014"], {
  cwd, shell: false, stdio: "inherit",
  env: { ...process.env, PYTHONPATH: root, DATABASE_URL: config.databaseUrl,
    MILVUS_COLLECTION_NAME: config.collection },
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("error", () => {
  console.error("Acceptance API process could not start.");
  cleanup();
  process.exitCode = 1;
});
child.on("exit", (code) => {
  cleanup();
  process.exitCode = code ?? 1;
});

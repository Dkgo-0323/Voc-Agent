// @vitest-environment node
import { describe, expect, it } from "vitest";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { loadScenario } from "../e2e/scenario.mjs";

describe("dataset scenario", () => {
  it("loads the shared default and a changed dataset without old prompts", () => {
    const scenario = loadScenario();
    expect(scenario.turns).toHaveLength(5);
    expect(scenario.turns[4].status).toBe("abstained");
    const root = mkdtempSync(path.join(tmpdir(), "voc-scenario-"));
    try {
      const filename = path.join(root, "scenario.json");
      scenario.report_week = 202601;
      scenario.turns[0].prompt = "Count reviews in week 202601.";
      scenario.turns[0].week_id = 202601;
      writeFileSync(filename, JSON.stringify(scenario));
      expect(loadScenario(filename).turns[0].week_id).toBe(202601);
      for (const patch of [{ report_week: 202153 }, { turns: [] }, { citation_text: " " }]) {
        writeFileSync(filename, JSON.stringify({ ...scenario, ...patch }));
        expect(() => loadScenario(filename)).toThrow();
      }
      scenario.turns[0].tools = ["unknown"];
      writeFileSync(filename, JSON.stringify(scenario));
      expect(() => loadScenario(filename)).toThrow();
      expect(() => loadScenario("relative.json")).toThrow();
    } finally { rmSync(root, { recursive: true }); }
  });
});

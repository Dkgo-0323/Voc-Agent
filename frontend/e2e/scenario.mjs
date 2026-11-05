import { readFileSync } from "node:fs";
import path from "node:path";

export function loadScenario(filename) {
  if (filename !== undefined && !path.isAbsolute(filename)) throw new Error("Use an absolute scenario path");
  const value = JSON.parse(readFileSync(filename ?? new URL("../../shared/acceptance/synthetic-scenario.json", import.meta.url), "utf8"));
  const week = (w) => {
    if (!Number.isInteger(w) || w < 101 || w > 999953) return false;
    const year = Math.floor(w / 100), number = w % 100;
    const jan1 = new Date(0); jan1.setUTCFullYear(year, 0, 1); jan1.setUTCHours(0, 0, 0, 0);
    const day = jan1.getUTCDay();
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return number >= 1 && number <= (day === 4 || (day === 3 && leap) ? 53 : 52);
  };
  const text = (t) => typeof t === "string" && t.trim().length > 0;
  if (!value || value.schema_version !== 1 || !text(value.report_sku) || !text(value.citation_text)
      || !week(value.report_week) || !Array.isArray(value.turns) || value.turns.length !== 5
      || value.turns.some(t => !t || !text(t.prompt) || !week(t.week_id)
        || !Array.isArray(t.tools) || t.tools.length === 0 || new Set(t.tools).size !== t.tools.length
        || t.tools.some(x => !["tool_sql", "tool_rag", "tool_report"].includes(x))
        || !["success", "partial", "abstained"].includes(t.status)
        || typeof t.require_citation !== "boolean" || (t.status === "abstained" && t.require_citation))) {
    throw new Error("Invalid acceptance scenario");
  }
  return value;
}

// The fix the (fake) coding agent applies for each known incident slug — keyed
// by slug, value is {repoPath: newFileContents}. A REAL coding agent generates
// these by reading the code; this fake just looks them up so the demo needs no LLM.
// (Stored as line arrays so backticks/${...} inside the code stay literal.)

const INGEST_FIXED = [
  "// Tiny data-ingest job — the service the watchdog watches (and will patch).",
  "// It sums the prices in a batch of records.",
  'import { emit } from "./applog.ts";',
  'import { RECORDS, type Rec } from "./records.ts";',
  "",
  "export function process(records: Rec[]): { total: number; processed: number } {",
  "  let total = 0;",
  "  let processed = 0;",
  "  for (const r of records) {",
  "    total += r.price ?? 0;",
  "    processed += 1;",
  "  }",
  "  return { total, processed };",
  "}",
  "",
  "export function main(): { total: number; processed: number } {",
  '  emit("INFO", "ingest: starting batch");',
  "  const result = process(RECORDS);",
  '  emit("INFO", `ingest: done total=${result.total} processed=${result.processed}/${RECORDS.length}`);',
  "  return result;",
  "}",
  "",
].join("\n");

const TEST_FIXED = [
  'import { test } from "node:test";',
  'import assert from "node:assert/strict";',
  'import { process as ingest } from "./ingest.ts";',
  "",
  'test("sums known prices", () => {',
  "  const { total, processed } = ingest([{ id: 1, price: 10 }, { id: 2, price: 5 }]);",
  "  assert.equal(total, 15);",
  "  assert.equal(processed, 2);",
  "});",
  "",
  'test("missing price is kept, not dropped", () => {',
  "  const { total, processed } = ingest([{ id: 1 }, { id: 2, price: 5 }]);",
  "  assert.equal(processed, 2);",
  "  assert.equal(total, 5);",
  "});",
  "",
].join("\n");

export const CANNED_FIXES: Record<string, Record<string, string>> = {
  "ingest-price-keyerror": {
    "app/ingest.ts": INGEST_FIXED,
    "app/ingest.test.ts": TEST_FIXED,
  },
};

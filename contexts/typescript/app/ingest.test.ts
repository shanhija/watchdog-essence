import { test } from "node:test";
import assert from "node:assert/strict";
import { process as ingest } from "./ingest.ts";

test("sums known prices", () => {
  const { total, processed } = ingest([{ id: 1, price: 10 }, { id: 2, price: 5 }]);
  assert.equal(total, 15);
  assert.equal(processed, 2);
});

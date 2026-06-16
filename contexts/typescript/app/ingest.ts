// Tiny data-ingest job — the service the watchdog watches (and will patch).
// It sums the prices in a batch of records.
import { emit } from "./applog.ts";
import { RECORDS, type Rec } from "./records.ts";

export function process(records: Rec[]): { total: number; processed: number } {
  let total = 0;
  let processed = 0;
  for (const r of records) {
    // BUG: assumes every record has a 'price'; drops the ones that don't.
    if (r.price === undefined) {
      emit("ERROR", `KeyError: "price" while processing record id=${r.id} (app/ingest.ts)`);
      continue;
    }
    total += r.price;
    processed += 1;
  }
  return { total, processed };
}

export function main(): { total: number; processed: number } {
  emit("INFO", "ingest: starting batch");
  const result = process(RECORDS);
  emit("INFO", `ingest: done total=${result.total} processed=${result.processed}/${RECORDS.length}`);
  return result;
}

// The app's logger. Appends one JSON object per line to a log file — your
// "log aggregation", such as it is. The log store reads this same file.
// Override the path with the APP_LOG env var.
import { appendFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

function logPath(): string {
  if (process.env.APP_LOG) return process.env.APP_LOG;
  const here = path.dirname(fileURLToPath(import.meta.url)); // .../app
  return path.join(here, "..", "app.log");
}

export function emit(level: string, text: string): void {
  appendFileSync(logPath(), JSON.stringify({ ts: Date.now() / 1000, level, text }) + "\n");
}

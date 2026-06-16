// Log store — reads the JSON-lines log the app writes. Your real log
// aggregation (Loki/CloudWatch/ELK/...) goes here instead. ESSENCE §4A.
import { existsSync, readFileSync } from "node:fs";

export interface LogLine {
  ts: number;
  level: string;
  text: string;
}

export class FileLogStore {
  path: string;
  constructor(p: string) {
    this.path = p;
  }

  fetch(since = 0, until = Infinity): LogLine[] {
    if (!existsSync(this.path)) return [];
    return readFileSync(this.path, "utf8")
      .split("\n")
      .filter((l) => l.trim().length > 0)
      .map((l) => JSON.parse(l) as LogLine)
      .filter((r) => r.ts >= since && r.ts <= until);
  }
}

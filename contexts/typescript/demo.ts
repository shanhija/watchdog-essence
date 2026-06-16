// End-to-end demo + acceptance check for the closed loop. Run it after the agent
// has built watchdog.ts:
//
//     node demo.ts
//
// It shows the buggy app logging errors, the watchdog opening a PR that fixes the
// app's own code, and — after "merging" that PR into a throwaway copy — the same
// app running clean. The repo's app/ is left untouched, so it's repeatable.
// Throws (non-zero exit) on any failure, so it doubles as the acceptance test.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const LOG = path.join(ROOT, "app.log");
const PRS = path.join(ROOT, ".prs");
const SLUG = "ingest-price-keyerror";

function sh(args: string[], cwd: string = ROOT, env: NodeJS.ProcessEnv = process.env): void {
  const r = spawnSync(process.execPath, args, { cwd, env, stdio: "inherit" });
  if (r.status !== 0) throw new Error(`command failed: node ${args.join(" ")}`);
}

function errorTexts(logPath: string): string[] {
  if (!existsSync(logPath)) return [];
  return readFileSync(logPath, "utf8")
    .split("\n").filter((l) => l.trim().length > 0)
    .map((l) => JSON.parse(l))
    .filter((r) => r.level === "ERROR")
    .map((r) => r.text);
}

function banner(t: string): void {
  console.log("\n" + "=".repeat(66) + `\n${t}\n` + "=".repeat(66));
}

function assert(cond: unknown, msg: string): void {
  if (!cond) throw new Error(msg);
}

// 1) BEFORE: the buggy app logs errors
banner("1) BEFORE  —  run the buggy app; it logs errors");
if (existsSync(LOG)) rmSync(LOG);
if (existsSync(PRS)) rmSync(PRS, { recursive: true, force: true });
sh(["run_app.ts"]);
const before = errorTexts(LOG);
for (const e of before) console.log("   LOG ERROR:", e);
assert(before.length > 0, "expected the buggy app to log errors");

// 2) WATCHDOG: read logs -> fix -> open a PR
banner("2) WATCHDOG  —  read the logs, draft a fix, open a PR");
sh(["watchdog.ts"]);
const prs = existsSync(PRS) ? readdirSync(PRS).sort() : [];
console.log("   PRs opened:", prs.length ? prs : "(none)");
assert(prs.includes(SLUG), `expected the watchdog to open a PR '${SLUG}'`);
console.log("   --- PR ---");
console.log(readFileSync(path.join(PRS, SLUG, "pr.md"), "utf8"));

// 3) MERGE into a throwaway copy and re-run
banner("3) MERGE the PR (you, the human) and re-run — errors should be gone");
const files = JSON.parse(readFileSync(path.join(PRS, SLUG, "files.json"), "utf8")) as Record<string, string>;
const work = mkdtempSync(path.join(tmpdir(), "watchdog-merge-"));
try {
  cpSync(path.join(ROOT, "app"), path.join(work, "app"), { recursive: true });
  for (const [rel, content] of Object.entries(files)) {
    const p = path.join(work, rel);
    mkdirSync(path.dirname(p), { recursive: true });
    writeFileSync(p, content);
  }
  writeFileSync(path.join(work, "run.ts"), 'import { main } from "./app/ingest.ts";\nmain();\n');
  const mergedLog = path.join(work, "app.log");
  sh(["run.ts"], work, { ...process.env, APP_LOG: mergedLog });
  const after = errorTexts(mergedLog);
  console.log("   errors after the fix:", after.length ? after : "(none)");
  assert(after.length === 0, "the merged fix should have eliminated the errors");
} finally {
  rmSync(work, { recursive: true, force: true });
}

banner("HEALED  —  the watchdog's PR fixed the code that produced the logs");

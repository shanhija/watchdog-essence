// End-to-end demo + acceptance check for the closed loop — colored and paced for
// screen recording, so a single run tells the whole story (problem -> the prompt
// -> the fix -> healed).
//
//     node demo.ts             # colored + paced, good for recording a GIF
//     DEMO_FAST=1 node demo.ts  # no pauses (quick check / acceptance)
//     NO_COLOR=1 node demo.ts   # plain text
//
// Run it after the agent has built watchdog.ts. The repo's app/ is left
// untouched, so it's repeatable. Throws (non-zero exit) on any failure.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const LOG = path.join(ROOT, "app.log");
const PRS = path.join(ROOT, ".prs");
const SLUG = "ingest-price-keyerror";
const FAST = Boolean(process.env.DEMO_FAST);
const PROMPT = "Build me a service from this essence in this context.";

// --- color ---------------------------------------------------------------
const COLOR = (Boolean(process.env.FORCE_COLOR) || Boolean(process.stdout.isTTY)) && !process.env.NO_COLOR;

function c(code: string): (s: string) => string {
  return COLOR ? (s) => `\x1b[${code}m${s}\x1b[0m` : (s) => s;
}

const bold = c("1");
const dim = c("2");
const red = c("31");
const green = c("32");
const cyan = c("36");
const magenta = c("35");
const brgreen = c("92");
const brred = c("91");

function chip(text: string | number, bg: number): string {
  return COLOR ? `\x1b[1;97;${bg}m ${text} \x1b[0m` : `[${text}]`;
}

function rule(width = 66): string {
  return dim("─".repeat(width));
}

function sleep(ms: number): void {
  if (FAST) return;
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function typeOut(text: string, code = "1;97", delay = 22): void {
  if (COLOR) process.stdout.write(`\x1b[${code}m`);
  for (const ch of text) {
    process.stdout.write(ch);
    sleep(delay);
  }
  if (COLOR) process.stdout.write("\x1b[0m");
  process.stdout.write("\n");
}

function step(n: number, title: string, bg: number): void {
  console.log();
  console.log(`${chip(n, bg)} ${bold(title)}`);
  console.log(rule());
}

function errorTexts(logPath: string): string[] {
  if (!existsSync(logPath)) return [];
  return readFileSync(logPath, "utf8")
    .split("\n").filter((l) => l.trim().length > 0)
    .map((l) => JSON.parse(l))
    .filter((r) => r.level === "ERROR")
    .map((r) => r.text);
}

function parsePr(p: string): { title: string; body: string; diff: string } {
  const raw = readFileSync(p, "utf8");
  const head = raw.split("```diff")[0].split("\n").map((l) => l.trim()).filter((l) => l.length > 0);
  const title = (head[0] ?? "").replace(/^#+\s*/, "");
  const body = head[1] ?? "";
  const m = raw.match(/```diff\n([\s\S]*?)```/);
  const diff = m ? m[1] : "";
  return { title, body, diff };
}

function renderDiff(diff: string): void {
  for (const line of diff.replace(/\n$/, "").split("\n")) {
    let out: string;
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff --git")) out = bold(line);
    else if (line.startsWith("@@")) out = cyan(line);
    else if (line.startsWith("+")) out = green(line);
    else if (line.startsWith("-")) out = red(line);
    else out = dim(line);
    console.log("   " + out);
    sleep(30);
  }
}

function sh(args: string[], cwd: string = ROOT, env: NodeJS.ProcessEnv = process.env): void {
  const r = spawnSync(process.execPath, args, { cwd, env, stdio: "inherit" });
  if (r.status !== 0) throw new Error(`command failed: node ${args.join(" ")}`);
}

// --- the demo ------------------------------------------------------------
console.log();
console.log("   " + bold(cyan("watchdog-essence")) + dim("  ·  typescript context"));

// 1) BEFORE: the buggy app logs errors
step(1, "BEFORE  —  run the buggy app; it logs errors", 41);
if (existsSync(LOG)) rmSync(LOG);
if (existsSync(PRS)) rmSync(PRS, { recursive: true, force: true });
sh(["run_app.ts"]);
const before = errorTexts(LOG);
for (const e of before) {
  console.log("   " + brred("✗") + " " + e);
  sleep(300);
}
if (before.length === 0) throw new Error("expected the buggy app to log errors");
sleep(900);

// 2) THE PROMPT: build a watchdog from the essence
step(2, "THE PROMPT  —  hand your coding agent the essence + one line", 45);
sleep(400);
console.log();
console.log("   " + dim("So you tell your coding agent (Claude, Cursor, …):"));
console.log();
process.stdout.write("   " + dim("you") + " " + magenta("▸") + " ");
typeOut(`"${PROMPT}"`);
sleep(500);
console.log();
console.log("   " + dim("→ a coding agent reads ") + cyan("ESSENCE.md") + dim(" + ") + cyan("AGENTS.md")
  + dim(" and writes ") + cyan("watchdog.ts") + dim("."));
console.log("   " + dim("  (try it yourself — here we just run the watchdog it produces.)"));
sleep(900);

// 3) WATCHDOG: read logs -> fix -> open a PR
step(3, "WATCHDOG  —  read the logs, draft a fix, open a PR", 44);
console.log("   " + dim("running watchdog.ts …"));
const proc = spawnSync(process.execPath, ["watchdog.ts"], { cwd: ROOT, encoding: "utf8" });
if (proc.status !== 0) {
  process.stdout.write(proc.stdout ?? "");
  process.stderr.write(proc.stderr ?? "");
  console.error(brred("watchdog.ts isn't built yet — see AGENTS.md (or `cp watchdog.reference.ts watchdog.ts` to record)."));
  process.exit(1);
}
const prs = existsSync(PRS) ? readdirSync(PRS).sort() : [];
if (!prs.includes(SLUG)) throw new Error(`expected the watchdog to open a PR '${SLUG}'`);
const { body, diff } = parsePr(path.join(PRS, SLUG, "pr.md"));
sleep(400);
console.log();
console.log("   " + green("✓") + " " + bold("watchdog opened a pull request") + dim(`  (${SLUG})`));
if (body) console.log("   " + dim("  root cause: ") + body);
console.log();
console.log("   " + dim("patch ") + rule(58));
sleep(1000);
renderDiff(diff);
console.log("   " + rule(64));
console.log("   " + dim("note — here, triage + the fix are deterministic stand-ins (no API key)."));
sleep(1000);

// 4) MERGE + AFTER
step(4, "MERGE the PR (you, the human) and re-run", 42);
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
  if (after.length) {
    for (const e of after) console.log("   " + brred("✗ ") + e);
  } else {
    console.log("   " + green("✓ no errors — the app runs clean."));
  }
  if (after.length) throw new Error("the merged fix should have eliminated the errors");
} finally {
  rmSync(work, { recursive: true, force: true });
}
sleep(700);

// finale
console.log();
console.log(green("─".repeat(66)));
console.log("   " + brgreen(bold("✓  HEALED")) + "   " + dim("the watchdog's PR fixed the code that produced the logs."));
console.log(green("─".repeat(66)));
console.log("   " + dim("real here: the essence, the pipeline, the sandboxed test, the diff."));
console.log("   " + dim("stand-ins here: the model (triage) + the coding agent — swap in your own."));

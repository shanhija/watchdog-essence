// Sandbox — an isolated copy of the app where a fix can be drafted and tested
// without touching your working tree. Here it's a temp dir + a subprocess; swap
// for a container/VM (ESSENCE §4E). The non-negotiable is pristine + isolated.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

export class LocalSandbox {
  dir: string;
  orig = new Map<string, string>();

  constructor(srcRoot: string) {
    this.dir = mkdtempSync(path.join(tmpdir(), "watchdog-sandbox-"));
    cpSync(path.join(srcRoot, "app"), path.join(this.dir, "app"), { recursive: true });
  }

  writeFiles(files: Record<string, string>): void {
    for (const [rel, content] of Object.entries(files)) {
      const p = path.join(this.dir, rel);
      if (!this.orig.has(rel)) this.orig.set(rel, existsSync(p) ? readFileSync(p, "utf8") : "");
      mkdirSync(path.dirname(p), { recursive: true });
      writeFileSync(p, content);
    }
  }

  runTests(): { passed: boolean; output: string } {
    const res = spawnSync(process.execPath, ["--test", "app/ingest.test.ts"], {
      cwd: this.dir, encoding: "utf8",
      env: { ...process.env, APP_LOG: path.join(this.dir, "sandbox.log") },
    });
    return { passed: res.status === 0, output: (res.stdout ?? "") + (res.stderr ?? "") };
  }

  diff(): string {
    let out = "";
    for (const [rel, orig] of this.orig) {
      const next = readFileSync(path.join(this.dir, rel), "utf8");
      if (next === orig) continue;
      out += unifiedDiff(rel, orig, next);
    }
    return out;
  }

  cleanup(): void {
    rmSync(this.dir, { recursive: true, force: true });
  }
}

// A compact unified diff for a single localized change region (enough for the
// canned fixes here). Real tooling would use a full LCS diff.
function unifiedDiff(rel: string, a: string, b: string): string {
  const al = a.split("\n");
  const bl = b.split("\n");
  let p = 0;
  while (p < al.length && p < bl.length && al[p] === bl[p]) p++;
  let sa = al.length;
  let sb = bl.length;
  while (sa > p && sb > p && al[sa - 1] === bl[sb - 1]) {
    sa--;
    sb--;
  }
  const ctx = 3;
  const start = Math.max(0, p - ctx);
  const aEnd = Math.min(al.length, sa + ctx);
  const lines: string[] = [];
  for (let i = start; i < p; i++) lines.push(" " + al[i]);
  for (let i = p; i < sa; i++) lines.push("-" + al[i]);
  for (let i = p; i < sb; i++) lines.push("+" + bl[i]);
  for (let i = sa; i < aEnd; i++) lines.push(" " + al[i]);
  const header = `@@ -${start + 1},${aEnd - start} +${start + 1},${bEnd(start, sb, sa, aEnd)} @@`;
  return `--- a/${rel}\n+++ b/${rel}\n${header}\n${lines.join("\n")}\n`;
}

function bEnd(start: number, sb: number, sa: number, aEnd: number): number {
  return sb - start + (aEnd - sa);
}

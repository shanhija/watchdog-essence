// Coding agent — given an incident and a sandbox, drafts a fix and runs the
// app's tests (the smoke gate). `CannedCodingAgent` recognizes a small set of
// seeded bugs and applies the known fix. A real agent investigates and writes
// the patch itself — implement `CLICodingAgent` (ESSENCE §4E, §6.2).
import { CANNED_FIXES } from "./fixes.ts";
import type { Incident } from "./triage_model.ts";
import type { LocalSandbox } from "./sandbox.ts";

export interface FixResult {
  status: string; // succeeded | smoke_failed | diff_empty | deferred
  diff: string;
  files: Record<string, string>;
  smokePassed: boolean;
  smokeOutput: string;
  narrative: string;
}

export class CannedCodingAgent {
  attemptFix(incident: Incident, sandbox: LocalSandbox): FixResult {
    const fix = CANNED_FIXES[incident.slug];
    if (!fix) {
      return {
        status: "deferred", diff: "", files: {}, smokePassed: false, smokeOutput: "",
        narrative: `No canned fix for '${incident.slug}'. A real coding agent would write one.`,
      };
    }
    sandbox.writeFiles(fix);
    const { passed, output } = sandbox.runTests();
    const diff = sandbox.diff();
    if (!diff) {
      return { status: "diff_empty", diff: "", files: {}, smokePassed: passed, smokeOutput: output, narrative: "no change produced" };
    }
    return {
      status: passed ? "succeeded" : "smoke_failed",
      diff, files: fix, smokePassed: passed, smokeOutput: output,
      narrative: "applied the fix and ran the app's tests in the sandbox",
    };
  }
}

export class CLICodingAgent {
  attemptFix(_incident: Incident, _sandbox: LocalSandbox): FixResult {
    throw new Error("Wire your coding agent — ESSENCE.md §6.2.");
  }
}

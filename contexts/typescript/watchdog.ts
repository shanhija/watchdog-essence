// BUILD ME — this is the watchdog, and it does not exist yet.
//
// This environment has a running app (app/) that logs errors, plus the services
// you need (services/). There is no watchdog. Build one here from the spec in
// ../../ESSENCE.md that:
//
//     reads the app's logs (log store)
//       -> triages them into incidents (triage model)
//       -> for each actionable incident, drafts a fix to the app's OWN code in a
//          sandbox and runs the app's tests (sandbox + coding agent)
//       -> opens a PR with the fix (code host)
//       -> reports it (notifier)
//
// Goal: `node demo.ts` ends with "HEALED". See AGENTS.md for the service APIs and
// ESSENCE.md §4 for the pipeline (and §2 — never touch the real working tree; a
// human merges the PR).

throw new Error(
  "Build the watchdog here — see AGENTS.md (the service catalog) and ESSENCE.md §4. " +
    "Wire: log_store -> triage_model -> (sandbox + coding_agent) -> code_host -> notifier.",
);

// Notifier — delivers the one-per-incident report. This fake prints it; swap
// for email/chat/ticketing (ESSENCE §10).
export interface Report {
  slug: string;
  severity: string;
  confidence: string;
  summary: string;
  rootCause: string;
  fixStatus: string;
  prUrl: string | null;
}

export class ConsoleNotifier {
  send(r: Report): void {
    console.log("\n  --- INCIDENT REPORT ---------------------------------------");
    console.log(`    incident : ${r.slug}  [${r.severity}/${r.confidence}]`);
    console.log(`    summary  : ${r.summary}`);
    console.log(`    root     : ${r.rootCause}`);
    console.log(`    fix      : ${r.fixStatus}`);
    if (r.prUrl) console.log(`    PR       : ${r.prUrl}`);
    console.log("  -----------------------------------------------------------");
  }
}

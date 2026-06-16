// Triage model — clusters log lines into incidents and classifies them.
// `FakeTriage` is deterministic (no API key): it groups by a normalized
// signature and recognizes a couple of known error shapes. A real model reads
// the content instead — implement `LLMTriage` (ESSENCE §6.1).

type Line = { level: string; text: string };

export interface Incident {
  slug: string;
  severity: string; // noop | low | medium | high
  confidence: string; // low | medium | high
  rootCause: string;
  summary: string;
  affectedFiles: string[];
  sampleLines: string[];
  occurrences: number;
}

export class FakeTriage {
  cluster(lines: Line[]): Incident[] {
    const errs = lines.filter((l) => l.level === "WARN" || l.level === "ERROR");
    const groups = new Map<string, Line[]>();
    for (const l of errs) {
      const sig = l.text.replace(/\d+/g, "#"); // mask numbers so ids don't split a bug
      let arr = groups.get(sig);
      if (!arr) {
        arr = [];
        groups.set(sig, arr);
      }
      arr.push(l);
    }
    return [...groups.values()].map((ls) => this.classify(ls));
  }

  classify(ls: Line[]): Incident {
    const text = ls[0].text;
    const samples = ls.slice(0, 3).map((l) => l.text);
    if (text.includes("KeyError") && text.includes("price")) {
      return {
        slug: "ingest-price-keyerror", severity: "medium", confidence: "high",
        rootCause: "app/ingest.ts assumes every record has a 'price' and drops the ones that don't",
        summary: "Ingest drops records missing a 'price' field (logging an error for each)",
        affectedFiles: ["app/ingest.ts"], sampleLines: samples, occurrences: ls.length,
      };
    }
    return {
      slug: "unclassified-error", severity: "low", confidence: "low",
      rootCause: "unknown", summary: text.slice(0, 80),
      affectedFiles: [], sampleLines: samples, occurrences: ls.length,
    };
  }
}

export class LLMTriage {
  model: string;
  apiKey: string;
  constructor(o: { model: string; apiKey: string }) {
    this.model = o.model;
    this.apiKey = o.apiKey;
  }

  cluster(_lines: Line[]): Incident[] {
    throw new Error("Wire your LLM here — ESSENCE.md §6.1.");
  }
}

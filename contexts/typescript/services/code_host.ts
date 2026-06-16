// Code host — opens pull requests. This fake records each PR under `.prs/<slug>/`
// (a human-readable patch + the patched file contents, so a reviewer can merge it).
// Swap for your git host's PR API (ESSENCE §4H).
import { existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";

export class LocalCodeHost {
  prsDir: string;
  constructor(prsDir: string) {
    this.prsDir = prsDir;
  }

  openPr(slug: string, title: string, body: string, diff: string, files: Record<string, string>): string {
    const d = path.join(this.prsDir, slug);
    mkdirSync(d, { recursive: true });
    writeFileSync(path.join(d, "pr.md"), `# ${title}\n\n${body}\n\n\`\`\`diff\n${diff}\`\`\`\n`);
    writeFileSync(path.join(d, "files.json"), JSON.stringify(files));
    return `file://${d}`;
  }

  listPrs(): string[] {
    if (!existsSync(this.prsDir)) return [];
    return readdirSync(this.prsDir)
      .filter((n) => statSync(path.join(this.prsDir, n)).isDirectory())
      .sort();
  }
}

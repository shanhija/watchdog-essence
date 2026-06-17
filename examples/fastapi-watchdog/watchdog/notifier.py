"""Notifier + report rendering (ESSENCE §10, Appendix B).

Exactly one notification per incident, containing enough to act without opening anything
else. Rendering is a pure function (golden-file testable); the agent log is an attachment
(the body shows only a tail), capped so one runaway run can't get the notification rejected.

Infrastructure role — kept abstract. This environment has no notifier, so the default is
``FileNotifier`` (writes the report to a directory); an SMTP adapter is provided.
"""
from __future__ import annotations

import os
import time
from typing import Optional, Protocol

from .models import Incident, Report

_AGENT_LOG_TAIL_CHARS = 2000
_ATTACHMENT_CAP_CHARS = 200_000


def report_from_incident(inc: Incident) -> Report:
    return Report(
        incident_id=inc.id or 0,
        slug=inc.slug,
        severity=inc.severity,
        confidence=inc.confidence,
        summary=inc.summary,
        root_cause=inc.root_cause,
        sample_lines=inc.sample_lines,
        status=inc.status or "",
        diff=inc.diff or "",
        smoke_passed=inc.smoke_result,
        narrative=inc.narrative or "",
        pr_url=inc.pr_url,
        pr_skip_reason=inc.pr_skip_reason,
        triage_model=inc.triage_model or "",
        coding_agent_model=inc.coding_agent_model or "",
        dedup_verdict=inc.dedup_verdict,
        agent_log=inc.agent_log or "",
    )


def render_subject(report: Report) -> str:
    return f"[watchdog] {report.severity.upper()} {report.slug} — {report.status}"


def render_body(report: Report) -> str:
    """Render the report body as Markdown. Deterministic (no timestamps) for golden tests."""
    lines: list[str] = []
    lines.append(f"# {report.severity.upper()}: {report.slug}")
    lines.append("")
    lines.append(f"- **Confidence:** {report.confidence}")
    lines.append(f"- **Fix status:** {report.status}")
    smoke = "n/a" if report.smoke_passed is None else ("passed" if report.smoke_passed else "FAILED")
    lines.append(f"- **Smoke gate:** {smoke}")
    if report.pr_url:
        lines.append(f"- **Pull request:** {report.pr_url}")
    else:
        lines.append(f"- **Pull request:** none ({report.pr_skip_reason or 'n/a'})")
    if report.dedup_verdict:
        lines.append(f"- **Remedy dedup verdict:** {report.dedup_verdict}")
    lines.append(f"- **Models:** triage={report.triage_model or 'n/a'}, "
                 f"agent={report.coding_agent_model or 'n/a'}")
    lines.append("")
    lines.append("## Summary")
    lines.append(report.summary or "(none)")
    lines.append("")
    lines.append("## Root-cause hypothesis")
    lines.append(report.root_cause or "(none)")
    lines.append("")
    lines.append("## Sample log lines")
    if report.sample_lines:
        for s in report.sample_lines:
            lines.append(f"    {s}")
    else:
        lines.append("    (none)")
    lines.append("")
    lines.append("## Agent narrative")
    lines.append(report.narrative or "(none)")
    lines.append("")
    lines.append("## Diff")
    if report.diff.strip():
        lines.append("```diff")
        lines.append(report.diff.rstrip())
        lines.append("```")
    else:
        lines.append("(no diff)")
    if report.agent_log.strip():
        lines.append("")
        lines.append("## Agent log (tail; full log attached)")
        lines.append("```")
        lines.append(report.agent_log[-_AGENT_LOG_TAIL_CHARS:].strip())
        lines.append("```")
    return "\n".join(lines)


def render_attachment(report: Report) -> str:
    return report.agent_log[:_ATTACHMENT_CAP_CHARS]


class Notifier(Protocol):
    def send(self, report: Report) -> dict: ...


class FileNotifier:
    """Writes each report to a directory as a Markdown file (the default sink)."""

    def __init__(self, reports_dir: str) -> None:
        self.reports_dir = reports_dir
        os.makedirs(reports_dir, exist_ok=True)

    def send(self, report: Report) -> dict:
        try:
            base = f"{report.incident_id:06d}-{report.slug}"
            with open(os.path.join(self.reports_dir, base + ".md"), "w") as f:
                f.write(render_subject(report) + "\n\n" + render_body(report))
            attachment = render_attachment(report)
            if attachment.strip():
                with open(os.path.join(self.reports_dir, base + ".agent.log"), "w") as f:
                    f.write(attachment)
            return {"delivered": True}
        except Exception as exc:  # noqa: BLE001
            return {"delivered": False, "failure_reason": str(exc)}


class SmtpNotifier:
    """Delivers the report as an email with the agent log attached."""

    def __init__(self, *, host: str, port: int, user: str, password: str,
                 sender: str, recipients: str) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender
        self.recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    def send(self, report: Report) -> dict:
        import smtplib
        from email.message import EmailMessage

        try:
            msg = EmailMessage()
            msg["Subject"] = render_subject(report)
            msg["From"] = self.sender
            msg["To"] = ", ".join(self.recipients)
            msg.set_content(render_body(report))
            attachment = render_attachment(report)
            if attachment.strip():
                msg.add_attachment(
                    attachment.encode("utf-8"),
                    maintype="text", subtype="plain",
                    filename=f"{report.slug}.agent.log",
                )
            with smtplib.SMTP(self.host, self.port, timeout=30) as s:
                s.starttls()
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)
            return {"delivered": True}
        except Exception as exc:  # noqa: BLE001
            return {"delivered": False, "failure_reason": str(exc)}


class CollectingNotifier:
    """Test/dev notifier — keeps sent reports in memory."""

    def __init__(self) -> None:
        self.sent: list[Report] = []

    def send(self, report: Report) -> dict:
        self.sent.append(report)
        return {"delivered": True}

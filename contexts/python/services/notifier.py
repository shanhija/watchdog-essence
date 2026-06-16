"""Notifier — delivers the one-per-incident report. This fake prints it; swap
for email/chat/ticketing (ESSENCE §10)."""


class ConsoleNotifier:
    def send(self, report: dict) -> None:
        print("\n  --- INCIDENT REPORT ---------------------------------------")
        print(f"    incident : {report['slug']}  [{report['severity']}/{report['confidence']}]")
        print(f"    summary  : {report['summary']}")
        print(f"    root     : {report['root_cause']}")
        print(f"    fix      : {report['fix_status']}")
        if report.get("pr_url"):
            print(f"    PR       : {report['pr_url']}")
        print("  -----------------------------------------------------------")

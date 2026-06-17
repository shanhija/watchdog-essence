# Context: FastAPI + Loki + Claude (the "real" one)

The [`python/`](../python/) and [`typescript/`](../typescript/) contexts prove the
essence with *fakes* (no API key, deterministic stand-ins). **This one proves it against
real infrastructure**: a FastAPI app shipping logs to a real **Loki**, triaged and fixed
by **real Claude**.

## What's in the box

- `app/` — a tiny **FastAPI** key/value service with a real bug (`GET /items/{key}` 500s
  on a missing key) — the code the watchdog watches *and* patches.
- `docker-compose.yml` — the app + **Loki** (+ optional Grafana for eyeballing logs).

## Run it

```bash
# 1. Bring up the environment (app on :8000, Loki on :3100, Grafana on :3000):
docker compose up --build

# 2. Install the app's deps on the host (the sandbox runs the app's real pytest):
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

# 3. Generate traffic — some requests hit missing keys -> 500 -> ERROR logs in Loki:
./seed.sh
```
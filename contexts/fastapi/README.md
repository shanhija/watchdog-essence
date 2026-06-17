# kvstore — a tiny FastAPI service

A minimal key/value HTTP service that ships its logs to **Loki**, wired up with Docker
Compose. Deliberately small.

## Run it

```bash
docker compose up --build     # app on :8000, Loki on :3100, Grafana on :3000
./seed.sh                      # send some traffic (a few reads, a few errors)
```

Browse the logs in Grafana at http://localhost:3000 (anonymous), or query Loki's API on
:3100 directly.

## Endpoints

| Method | Path           | Does |
|---|---|---|
| `GET`  | `/items/{key}` | return the stored value for `key` |
| `POST` | `/items/{key}` | store/replace a value — body `{"value": "..."}` |
| `GET`  | `/healthz`     | liveness |

## Layout

- `app/` — the service (`app/main.py`) and its tests (`app/tests/`)
- `docker-compose.yml` — the app + Loki (+ Grafana)
- `Dockerfile`, `requirements.txt` — how the app image is built
- `seed.sh` — a small traffic generator
- `loki-config.yaml` — minimal Loki config

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest app/tests -q
```

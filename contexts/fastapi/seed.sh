#!/usr/bin/env bash
# Generate traffic against the kvstore app so Loki has both healthy and ERROR logs.
# Some requests hit keys that don't exist -> KeyError -> 500 -> an ERROR line in Loki.
#
#   ./seed.sh                      # against http://localhost:8000
#   ./seed.sh http://host:8000     # against a custom base URL
set -euo pipefail
BASE="${1:-http://localhost:8000}"
LOKI="${LOKI_URL:-http://localhost:3100}"

echo "seeding traffic against $BASE ..."
curl -fsS "$BASE/items/hello" >/dev/null && echo "  ok    GET  /items/hello"
curl -fsS -X POST "$BASE/items/order-42" -H 'content-type: application/json' \
  -d '{"value":"shipped"}' >/dev/null && echo "  ok    POST /items/order-42"

# Missing keys -> the bug fires. A few repeats and varied keys for some variety:
for k in order-99 user-7 sku-555 order-99 user-7; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/items/$k")
  echo "  boom  GET  /items/$k -> $code"
done

echo
echo "done. error lines are now in Loki. Query them:"
echo "  curl -s '$LOKI/loki/api/v1/query_range?query=%7Bservice%3D%22kvstore%22%2Clevel%3D%22ERROR%22%7D' | python3 -m json.tool"

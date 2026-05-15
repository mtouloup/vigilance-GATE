#!/usr/bin/env bash
# publish_event.sh — Example producer for the T5.3 Agentic Wrapper Framework
#
# Wraps a raw security event and publishes it to the pilot.events.raw queue
# so the vigilance-gate container picks it up and runs the full pipeline.
#
# Usage:
#   ./tools/publish_event.sh [OPTIONS] <event>
#
# Options:
#   -h, --host HOST       RabbitMQ host            (default: localhost)
#   -p, --port PORT       RabbitMQ management port  (default: 15672)
#   -u, --user USER       RabbitMQ username         (default: vigilance)
#   -P, --password PASS   RabbitMQ password         (default: vigilance)
#   -q, --queue QUEUE     Target queue              (default: pilot.events.raw)
#   --help                Show this help and exit
#
# The <event> argument is the raw log line or JSON object to publish.
# It is wrapped automatically as {"raw": <event>} before being sent.
#
# Examples:
#
#   # OTE brute-force alert (CEF format)
#   ./tools/publish_event.sh \
#     'CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH'
#
#   # Siemens OT anomaly (JSON format — use single quotes to avoid shell expansion)
#   ./tools/publish_event.sh \
#     '{"plc":"PLC-07","line":"Line-3","protocol":"OPC-UA","anomaly":"register_write_out_of_range","severity":"CRITICAL"}'
#
#   # Point at a remote RabbitMQ instance
#   ./tools/publish_event.sh -h broker.example.com -u myuser -P mypass \
#     'CEF:0|OTE-IDS|SOCv3|2.0|100|AUTH_FAIL|5|src=10.1.2.3 dst=nms-02 cnt=10 app=SSH'
#
#   # Inject a synthetic Digital Twin event from WP3 D-VISOR
#   ./tools/publish_event.sh -q dt.events.synthetic \
#     '{"plc":"PLC-01","anomaly":"voltage_spike","severity":"HIGH"}'

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
HOST="localhost"
PORT="15672"
USER="vigilance"
PASSWORD="vigilance"
QUEUE="pilot.events.raw"

# ── Argument parsing ──────────────────────────────────────────────────────────
usage() {
  sed -n '/^# Usage:/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--host)     HOST="$2";     shift 2 ;;
    -p|--port)     PORT="$2";     shift 2 ;;
    -u|--user)     USER="$2";     shift 2 ;;
    -P|--password) PASSWORD="$2"; shift 2 ;;
    -q|--queue)    QUEUE="$2";    shift 2 ;;
    --help)        usage ;;
    --)            shift; break ;;
    -*)            echo "Unknown option: $1" >&2; exit 1 ;;
    *)             break ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "Error: no event supplied." >&2
  echo "Run './tools/publish_event.sh --help' for usage." >&2
  exit 1
fi

RAW_EVENT="$1"

# ── Dependency check ──────────────────────────────────────────────────────────
if ! command -v curl &>/dev/null; then
  echo "Error: curl is required but not installed." >&2
  exit 1
fi

# ── Build payload ─────────────────────────────────────────────────────────────
# If the event looks like a JSON object/array, embed it directly so the
# pipeline receives {"raw": {...}} instead of {"raw": "{...}"}.
# Otherwise wrap it as a plain string.
if [[ "$RAW_EVENT" =~ ^\{.*\}$ || "$RAW_EVENT" =~ ^\[.*\]$ ]]; then
  PAYLOAD="{\"raw\": ${RAW_EVENT}}"
else
  # Escape double-quotes in the string for JSON safety
  ESCAPED=$(printf '%s' "$RAW_EVENT" | sed 's/\\/\\\\/g; s/"/\\"/g')
  PAYLOAD="{\"raw\": \"${ESCAPED}\"}"
fi

# ── Publish via RabbitMQ Management HTTP API ──────────────────────────────────
MGMT_URL="http://${HOST}:${PORT}/api/exchanges/%2F/amq.default/publish"

BODY=$(cat <<EOF
{
  "routing_key": "${QUEUE}",
  "payload": $(printf '%s' "$PAYLOAD" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
  "payload_encoding": "string",
  "properties": {
    "delivery_mode": 2,
    "content_type": "application/json"
  }
}
EOF
)

HTTP_STATUS=$(curl -s -o /tmp/vigilance_pub_response.txt -w "%{http_code}" \
  -u "${USER}:${PASSWORD}" \
  -H "Content-Type: application/json" \
  -X POST "${MGMT_URL}" \
  -d "${BODY}")

RESPONSE=$(cat /tmp/vigilance_pub_response.txt)

if [[ "$HTTP_STATUS" == "200" ]]; then
  ROUTED=$(echo "$RESPONSE" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("routed", "unknown"))' 2>/dev/null || echo "unknown")
  echo "Published to '${QUEUE}' on ${HOST}:${PORT} (routed=${ROUTED})"
  echo "Payload: ${PAYLOAD}"
else
  echo "Error: HTTP ${HTTP_STATUS}" >&2
  echo "${RESPONSE}" >&2
  exit 1
fi

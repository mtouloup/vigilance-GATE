#!/usr/bin/env bash
# simulate_t54.sh — Simulates a T5.4 orchestrator response for INTEGRATED mode testing
#
# In VIGILANCE_MODE=INTEGRATED the pipeline splits in two:
#   1. T5.3 receives a raw event on pilot.events.raw
#   2. T5.3 runs C1 normalisation and publishes a CanonicalEvent to t53.canonical_events
#   3. T5.4 (orchestrator) consumes the CanonicalEvent, calls T5.1 RAG, selects an
#      agent from T5.2, and dispatches an ActionRequest to t53.action_requests
#   4. T5.3 picks up the ActionRequest, runs C5 guardrail + C3+C4 execution, and
#      publishes an ExecutionResult to t53.results
#
# This script simulates step 3 — it can either:
#   a) Auto-mode (default): consume the next CanonicalEvent from t53.canonical_events
#      and derive a realistic ActionRequest for that sector
#   b) Manual mode (--no-consume + --event-id / --pilot / --actions): publish a
#      hand-crafted request without consuming from the queue
#
# Usage:
#   ./tools/simulate_t54.sh [OPTIONS]
#
# Options:
#   -h, --host HOST         RabbitMQ host              (default: localhost)
#   -p, --port PORT         RabbitMQ management port   (default: 15672)
#   -u, --user USER         RabbitMQ username          (default: vigilance)
#   -P, --password PASS     RabbitMQ password          (default: vigilance)
#   --event-id ID           Override event_id          (default: auto from queue)
#   --pilot PILOT           Pilot identifier           (default: auto from queue)
#   --actions ACTIONS       Comma-separated actions    (default: auto for sector)
#   --confidence FLOAT      Agent confidence 0.0-1.0   (default: 0.92)
#   --policy TEXT           NL policy update string    (default: none)
#   --no-consume            Skip consuming from t53.canonical_events; use --event-id
#   --purge                 Purge t53.canonical_events before waiting (clears stale events)
#   --wait SECS             Wait N seconds for a CanonicalEvent before giving up (default: 30)
#   --help                  Show this help and exit
#
# Tip — avoiding stale event_id mismatches:
#   If you see "not in cache" warnings it means a stale CanonicalEvent was sitting
#   in the queue from a previous run. Use --purge to clear the queue first:
#     ./tools/simulate_t54.sh --purge
#
# Workflow:
#   Step 1: Start the stack in INTEGRATED mode
#           VIGILANCE_MODE=INTEGRATED docker compose up --build
#
#   Step 2: Send a raw event (T5.3 will normalise and publish CanonicalEvent)
#           ./tools/publish_event.sh 'CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|...'
#
#   Step 3: Run this script to simulate T5.4 dispatching an ActionRequest
#           ./tools/simulate_t54.sh
#
#   Step 4: Check the ExecutionResult in t53.results
#           docker exec vigilance-rabbitmq rabbitmqadmin get queue=t53.results ackmode=ack_requeue_true
#
# Examples:
#
#   # Auto-mode: consume next CanonicalEvent and dispatch matching ActionRequest
#   ./tools/simulate_t54.sh
#
#   # Auto-mode with queue purge (recommended if you see event_id mismatch warnings)
#   ./tools/simulate_t54.sh --purge
#
#   # Manual: TELECOM — OTE/Greece
#   ./tools/simulate_t54.sh --no-consume \
#     --event-id evt-ote-001 --pilot OTE_GR \
#     --actions block_ip,revoke_session,notify_soc \
#     --confidence 0.96
#
#   # Manual: MARITIME — Port of Rotterdam
#   ./tools/simulate_t54.sh --no-consume \
#     --event-id evt-rot-001 --pilot Rotterdam_NL \
#     --actions block_vessel_access,quarantine_cargo_system,notify_port_authority,notify_soc \
#     --confidence 0.88
#
#   # Manual: FINANCE — CaixaBank
#   ./tools/simulate_t54.sh --no-consume \
#     --event-id evt-cai-001 --pilot CaixaBank_ES \
#     --actions freeze_account,block_transaction,notify_fraud_team,notify_soc \
#     --confidence 0.93
#
#   # Manual: INDUSTRY_4 — Siemens/Romania (with OT policy update for NL→Rego)
#   ./tools/simulate_t54.sh --no-consume \
#     --event-id evt-sie-001 --pilot Siemens_RO \
#     --actions isolate_plc,revoke_ot_session,notify_soc,update_zt_policy \
#     --confidence 0.91 \
#     --policy "Deny all OPC-UA traffic from Zone-B to Zone-A for 4 hours"

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
HOST="localhost"
PORT="15672"
USER="vigilance"
PASSWORD="vigilance"
WAIT_SECS=30
CONFIDENCE="0.92"
POLICY=""
OVERRIDE_EVENT_ID=""
OVERRIDE_PILOT=""
OVERRIDE_ACTIONS=""
NO_CONSUME=false
PURGE=false

# ── Argument parsing ──────────────────────────────────────────────────────────
usage() {
  sed -n '/^# Usage:/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--host)        HOST="$2";              shift 2 ;;
    -p|--port)        PORT="$2";              shift 2 ;;
    -u|--user)        USER="$2";              shift 2 ;;
    -P|--password)    PASSWORD="$2";          shift 2 ;;
    --event-id)       OVERRIDE_EVENT_ID="$2"; shift 2 ;;
    --pilot)          OVERRIDE_PILOT="$2";    shift 2 ;;
    --actions)        OVERRIDE_ACTIONS="$2";  shift 2 ;;
    --confidence)     CONFIDENCE="$2";        shift 2 ;;
    --policy)         POLICY="$2";            shift 2 ;;
    --wait)           WAIT_SECS="$2";         shift 2 ;;
    --no-consume)     NO_CONSUME=true;        shift ;;
    --purge)          PURGE=true;             shift ;;
    --help)           usage ;;
    --)               shift; break ;;
    -*)               echo "Unknown option: $1" >&2; exit 1 ;;
    *)                break ;;
  esac
done

# ── Dependency check ──────────────────────────────────────────────────────────
if ! command -v curl &>/dev/null; then
  echo "Error: curl is required but not installed." >&2; exit 1
fi
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required but not installed." >&2; exit 1
fi

MGMT_BASE="http://${HOST}:${PORT}"
AUTH="${USER}:${PASSWORD}"

# ── Helper: default actions per pilot ─────────────────────────────────────────
default_actions_for_pilot() {
  local pilot="$1"
  case "$pilot" in
    OTE_GR|TELECOM)
      echo '["block_ip","revoke_session","notify_soc"]' ;;
    Rotterdam_NL|MARITIME)
      echo '["block_vessel_access","quarantine_cargo_system","notify_port_authority","notify_soc"]' ;;
    CaixaBank_ES|FINANCE)
      echo '["freeze_account","block_transaction","notify_fraud_team","notify_soc"]' ;;
    Siemens_RO|INDUSTRY_4)
      echo '["isolate_plc","revoke_ot_session","notify_soc","update_zt_policy"]' ;;
    *)
      echo '["block_ip","notify_soc"]' ;;
  esac
}

# ── Optional: purge stale events from t53.canonical_events ───────────────────
if [[ "$PURGE" == "true" && "$NO_CONSUME" == "false" ]]; then
  echo "Purging stale events from t53.canonical_events..."
  PURGE_RESP=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "$AUTH" -X DELETE \
    "${MGMT_BASE}/api/queues/%2F/t53.canonical_events/contents")
  if [[ "$PURGE_RESP" == "204" ]]; then
    echo "Queue purged. Waiting for fresh CanonicalEvent from T5.3..."
  else
    echo "Warning: purge returned HTTP ${PURGE_RESP} — continuing anyway." >&2
  fi
fi

# ── Step 1: consume a CanonicalEvent from t53.canonical_events ─────────────────
EVENT_ID=""
PILOT=""

if [[ "$NO_CONSUME" == "false" ]]; then
  echo "Waiting up to ${WAIT_SECS}s for a CanonicalEvent on t53.canonical_events..."
  DEADLINE=$(( $(date +%s) + WAIT_SECS ))
  CANONICAL_JSON=""

  while [[ $(date +%s) -lt $DEADLINE ]]; do
    RESPONSE=$(curl -s -u "$AUTH" \
      -X POST "${MGMT_BASE}/api/queues/%2F/t53.canonical_events/get" \
      -H "Content-Type: application/json" \
      -d '{"count":1,"ackmode":"ack_requeue_false","encoding":"auto","truncate":50000}' \
      2>/dev/null || echo "[]")

    COUNT=$(echo "$RESPONSE" | python3 -c \
      "import json,sys; d=json.load(sys.stdin); print(len(d))" 2>/dev/null || echo 0)

    if [[ "$COUNT" -gt 0 ]]; then
      CANONICAL_JSON=$(echo "$RESPONSE" | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
payload = msgs[0]['payload']
if isinstance(payload, str):
    print(payload)
else:
    print(json.dumps(payload))
" 2>/dev/null || echo "")
      break
    fi
    sleep 1
  done

  if [[ -z "$CANONICAL_JSON" ]]; then
    echo "No CanonicalEvent received within ${WAIT_SECS}s." >&2
    echo "" >&2
    echo "Possible causes:" >&2
    echo "  • No raw event has been sent yet — run ./tools/publish_event.sh first" >&2
    echo "  • Stack is in STANDALONE mode — restart with VIGILANCE_MODE=INTEGRATED" >&2
    echo "  • T5.3 is still processing — increase --wait" >&2
    echo "" >&2
    echo "Or use --no-consume with --event-id and --pilot for manual dispatch." >&2
    exit 1
  fi

  echo "Received CanonicalEvent from t53.canonical_events:"
  echo "$CANONICAL_JSON" | python3 -m json.tool 2>/dev/null || echo "$CANONICAL_JSON"
  echo ""

  # Extract event_id and pilot
  EVENT_ID=$(echo "$CANONICAL_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('event_id', ''))
" 2>/dev/null || echo "")

  PILOT=$(echo "$CANONICAL_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
mapping = {
    'TELECOM':    'OTE_GR',
    'MARITIME':   'Rotterdam_NL',
    'FINANCE':    'CaixaBank_ES',
    'INDUSTRY_4': 'Siemens_RO',
}
pilot = d.get('pilot', 'TELECOM')
print(mapping.get(pilot, pilot))
" 2>/dev/null || echo "OTE_GR")
fi

# ── Step 2: apply overrides ────────────────────────────────────────────────────
[[ -n "$OVERRIDE_EVENT_ID" ]] && EVENT_ID="$OVERRIDE_EVENT_ID"
[[ -n "$OVERRIDE_PILOT"   ]] && PILOT="$OVERRIDE_PILOT"

if [[ -z "$EVENT_ID" ]]; then
  EVENT_ID="evt-t54-sim-$(date +%s)"
  echo "Warning: could not extract event_id — using generated: ${EVENT_ID}" >&2
fi
if [[ -z "$PILOT" ]]; then
  PILOT="OTE_GR"
  echo "Warning: could not extract pilot — defaulting to: ${PILOT}" >&2
fi

# ── Step 3: determine actions ──────────────────────────────────────────────────
if [[ -n "$OVERRIDE_ACTIONS" ]]; then
  ACTIONS_JSON=$(python3 -c "
import json
actions = [a.strip() for a in '${OVERRIDE_ACTIONS}'.split(',') if a.strip()]
print(json.dumps(actions))
")
else
  ACTIONS_JSON=$(default_actions_for_pilot "$PILOT")
fi

# ── Step 4: generate request_id ───────────────────────────────────────────────
REQUEST_ID="req-t54-sim-$(date +%s)-$$"

# ── Step 5: build ActionRequest payload ───────────────────────────────────────
ACTION_REQUEST=$(python3 -c "
import json

d = {
    'request_id':       '${REQUEST_ID}',
    'event_id':         '${EVENT_ID}',
    'pilot':            '${PILOT}',
    'actions':          ${ACTIONS_JSON},
    'agent_confidence': ${CONFIDENCE},
}
policy = '''${POLICY}'''
if policy.strip():
    d['policy_update'] = policy
print(json.dumps(d))
")

# ── Step 6: publish to t53.action_requests ────────────────────────────────────
ENVELOPE=$(python3 -c "
import json
action_request = json.loads('''${ACTION_REQUEST}''')
envelope = {
    'routing_key': 't53.action_requests',
    'payload': json.dumps(action_request),
    'payload_encoding': 'string',
    'properties': {
        'delivery_mode': 2,
        'content_type': 'application/json',
    }
}
print(json.dumps(envelope))
")

echo "Dispatching ActionRequest to t53.action_requests (simulating T5.4 orchestrator):"
echo "$ACTION_REQUEST" | python3 -m json.tool 2>/dev/null || echo "$ACTION_REQUEST"
echo ""

HTTP_STATUS=$(curl -s -o /tmp/vigilance_t54_response.txt -w "%{http_code}" \
  -u "$AUTH" \
  -H "Content-Type: application/json" \
  -X POST "${MGMT_BASE}/api/exchanges/%2F/amq.default/publish" \
  -d "$ENVELOPE")

RESPONSE=$(cat /tmp/vigilance_t54_response.txt)

if [[ "$HTTP_STATUS" == "200" ]]; then
  ROUTED=$(echo "$RESPONSE" | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print(d.get("routed","unknown"))' 2>/dev/null || echo "unknown")
  echo "ActionRequest published (routed=${ROUTED})"
  echo ""
  echo "T5.3 will now run: C5 guardrail → C3+C4 execution → t53.results"
  echo ""
  echo "Check the ExecutionResult:"
  echo "  docker exec vigilance-rabbitmq rabbitmqadmin get queue=t53.results ackmode=ack_requeue_true"
else
  echo "Error: HTTP ${HTTP_STATUS}" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

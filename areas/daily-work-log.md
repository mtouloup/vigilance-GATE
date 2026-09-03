# Daily Work Log — VIGILANCE T5.3

---

## 2026-09-03

- **Fix: OPA parse validation — stdin not supported** (`vigilance/components/c3_execution/policy_translator.py`): `opa parse -` treats `-` as a literal filename, not stdin, causing `open -: no such file or directory` on every Rego validation attempt. Fixed by writing Rego candidate to a `NamedTemporaryFile` with `.rego` suffix, passing the path to `opa parse`, and cleaning up in `finally`. Also corrected error capture from `stderr` to `stdout or stderr` (OPA emits parse errors to stdout as JSON). Committed and pushed to branch `claude/setup-vigilance-t5-3-7HVrt` (PR #55).

- **Fix: LLM echoing `<pilot_lower>` placeholder in Rego package name** (`vigilance/components/c3_execution/policy_translator.py`): The system prompt used angle-bracket template notation (`vigilance.<pilot_lower>.<domain>`) which the LLM was outputting verbatim, causing OPA parse to fail after both attempts and fall back to `default deny = true`. Replaced with all-caps `PILOT`/`DOMAIN` convention, added concrete examples (`vigilance.siemens.ot`, `vigilance.ote.auth`), and added explicit rule "NEVER output the word PILOT or DOMAIN literally". Committed to same branch.

- **Demo artifact — Step 4 (Result & Audit) source picker**: Added `capturedRequestIdKnown` and `capturedRequestIdLLM` variables to track which Step 1 path (OT JSON / LLM) each pipeline execution came from. Added pill buttons in Step 4 to select which event's `request_id` to use for result/audit retrieval. Added three live API sections directly in Step 4: `GET /results/{id}`, `GET /audit`, `GET /audit/{id}`.

- **Demo artifact — Pilot scenario picker**: Added a scenario selector to the sidebar header with Siemens (INDUSTRY_4) active and three TODO placeholders: OTE (TELECOM), MARITIME sector, FINANCE sector. Maritime and Finance are labeled by sector only (no org names) per CLAUDE.md pilot-scope constraint.

- **Demo artifact — C4 Tool Dispatch step**: Inserted new "📤 C4 — Tool Dispatch" sidebar step between Full Pipeline and Result & Audit. Shows verb→plugin→tool routing table for the Siemens scenario, the `t53.actions.dispatch` broker message format, a stub-adapter warning (M10–M15 for real implementations), and a live section fetching `action_results` from the last execution result.

"""Generate T5.3 Implementation Summary PDF using reportlab."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from datetime import date

OUTPUT = "T5.3_Implementation_Summary_M6.pdf"

# ── Colour palette ─────────────────────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1a3a5c")
MID_BLUE    = colors.HexColor("#2563a8")
LIGHT_BLUE  = colors.HexColor("#dbeafe")
ACCENT      = colors.HexColor("#0ea5e9")
LIGHT_GREY  = colors.HexColor("#f1f5f9")
MID_GREY    = colors.HexColor("#94a3b8")
DARK_GREY   = colors.HexColor("#334155")
GREEN       = colors.HexColor("#16a34a")
ORANGE      = colors.HexColor("#ea580c")
WHITE       = colors.white

# ── Styles ─────────────────────────────────────────────────────────────────────
base = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, parent=base["Normal"], **kw)

styles = {
    "title":    S("title",    fontSize=22, textColor=WHITE,     leading=28, spaceAfter=4,  fontName="Helvetica-Bold"),
    "subtitle": S("subtitle", fontSize=11, textColor=LIGHT_BLUE, leading=16, spaceAfter=2,  fontName="Helvetica"),
    "h1":       S("h1",       fontSize=13, textColor=DARK_BLUE,  leading=18, spaceBefore=14, spaceAfter=4, fontName="Helvetica-Bold"),
    "h2":       S("h2",       fontSize=10, textColor=MID_BLUE,   leading=14, spaceBefore=8,  spaceAfter=3, fontName="Helvetica-Bold"),
    "body":     S("body",     fontSize=9,  textColor=DARK_GREY,  leading=14, spaceAfter=4,  fontName="Helvetica"),
    "bullet":   S("bullet",   fontSize=9,  textColor=DARK_GREY,  leading=13, spaceAfter=2,  leftIndent=12, fontName="Helvetica",
                              bulletIndent=4),
    "code":     S("code",     fontSize=8,  textColor=DARK_BLUE,  leading=12, spaceAfter=2,  fontName="Courier",
                              backColor=LIGHT_GREY, leftIndent=8, rightIndent=8, borderPadding=4),
    "tag":      S("tag",      fontSize=8,  textColor=WHITE,      leading=12, fontName="Helvetica-Bold"),
    "caption":  S("caption",  fontSize=8,  textColor=MID_GREY,   leading=11, fontName="Helvetica", alignment=TA_CENTER),
    "stub":     S("stub",     fontSize=9,  textColor=ORANGE,     leading=13, fontName="Helvetica-Bold"),
}

def hr(): return HRFlowable(width="100%", thickness=0.5, color=LIGHT_BLUE, spaceAfter=6, spaceBefore=2)
def sp(h=6): return Spacer(1, h)
def p(text, style="body"): return Paragraph(text, styles[style])
def b(text): return Paragraph(f"• {text}", styles["bullet"])
def h1(text): return p(text, "h1")
def h2(text): return p(text, "h2")

def table(headers, rows, col_widths=None, header_bg=DARK_BLUE, zebra=True):
    data = [headers] + rows
    if col_widths is None:
        col_widths = [A4[0] / len(headers) - 2*cm / len(headers)] * len(headers)

    header_cells = [Paragraph(h, ParagraphStyle("th", fontSize=8, textColor=WHITE,
                                                 fontName="Helvetica-Bold", leading=11)) for h in headers]
    body_cells = [[Paragraph(str(c), ParagraphStyle("td", fontSize=8, textColor=DARK_GREY,
                                                     fontName="Helvetica", leading=11)) for c in r] for r in rows]
    full_data = [header_cells] + body_cells

    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY] if zebra else [WHITE]),
        ("GRID", (0, 0), (-1, -1), 0.3, MID_GREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])
    return Table(full_data, colWidths=col_widths, style=style, repeatRows=1)

def cover_table():
    """Blue cover block built as a single-cell table."""
    content = [
        [Paragraph("VIGILANCE — GAP-101249737", ParagraphStyle("ct", fontSize=9, textColor=ACCENT,
                                                                 fontName="Helvetica-Bold", leading=13))],
        [Paragraph("T5.3 Agentic Wrapper Framework", ParagraphStyle("ct2", fontSize=22, textColor=WHITE,
                                                                      fontName="Helvetica-Bold", leading=28))],
        [Paragraph("Implementation Summary — M6", ParagraphStyle("ct3", fontSize=13, textColor=LIGHT_BLUE,
                                                                   fontName="Helvetica", leading=18))],
        [Spacer(1, 8)],
        [Paragraph(f"Lead: INNOV  ·  Date: {date.today().strftime('%B %Y')}  ·  Branch: claude/setup-vigilance-t5-3-7HVrt",
                   ParagraphStyle("ct4", fontSize=8, textColor=MID_GREY, fontName="Helvetica", leading=12))],
    ]
    t = Table(content, colWidths=[A4[0] - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 24),
        ("RIGHTPADDING", (0, 0), (-1, -1), 24),
        ("TOPPADDING", (0, 0), (0, 0), 28),
        ("BOTTOMPADDING", (0, -1), (0, -1), 28),
        ("TOPPADDING", (0, 1), (-1, -2), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -2), 4),
    ]))
    return t

# ── Document ───────────────────────────────────────────────────────────────────
def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
        title="T5.3 Agentic Wrapper Framework — Implementation Summary M6",
        author="INNOV / VIGILANCE T5.3",
    )

    W = A4[0] - 4*cm  # usable width

    story = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story += [cover_table(), sp(16)]

    story += [
        p("T5.3 is a single Python container that serves all four VIGILANCE GA pilots simultaneously "
          "(OTE/TELECOM · Siemens/INDUSTRY_4 · Rotterdam/MARITIME · CaixaBank/FINANCE). "
          "It is the operational bridge between raw security events and the cybersecurity tools that respond to them. "
          "Pilot detection happens per-event in C1 — no restart or reconfiguration is needed to switch between pilots.", "body"),
        sp(4),
    ]

    # ── 6-Component Architecture ───────────────────────────────────────────────
    story += [h1("Architecture — 6 Components"), hr()]

    # C1
    story += [h2("C1 — Event Ingestion & Normalization"), sp(2)]
    story += [
        p("Converts any raw security event into a structured <b>CanonicalEvent</b>. Five parsers tried in priority order:", "body"),
        sp(2),
        table(
            ["Parser", "Handles", "Pilot detection"],
            [
                ["OTJsonParser",  "Siemens OPC-UA / Modbus JSON",          "Hard-wires INDUSTRY_4"],
                ["CEFParser",     "ArcSight Common Event Format",           "From CEF fields"],
                ["ECSParser",     "Elastic Common Schema",                  "From agent.type keywords"],
                ["SyslogParser",  "RFC 3164 syslog",                        "Emits UNKNOWN"],
                ["LLMParser",     "Fallback — any unknown format (mistral:7b)", "LLM extraction, validated"],
            ],
            col_widths=[W*0.22, W*0.44, W*0.34],
        ),
        sp(4),
        p("The LLM is explicitly instructed never to guess the pilot — returns null for ambiguous events. "
          "UNKNOWN pilot falls back to TELECOM profile with a warning log.", "body"),
        sp(2),
        p("<b>CanonicalEvent fields:</b> core (event_id, type, severity, src_ip, target, pilot, timestamp) + "
          "pilot-specific extensions: telecom (subscriber_id, imsi, cell_id), OT (plc_id, scada_zone, ot_protocol, ot_safety_flag), "
          "maritime (vessel_id, port_zone, ais_mmsi), finance (account_id, transaction_id, fraud_score).", "body"),
        sp(6),
    ]

    # C2
    story += [h2("C2 — Agentic Interaction Layer (mistral-nemo)"), sp(2)]
    story += [
        p("Multi-turn tool-calling loop (up to 5 turns). For each event: receives CanonicalEvent + sector LLM prompt → "
          "may call tools → produces <b>AgentDecision</b> (threat type, recommended actions, confidence score).", "body"),
        sp(2),
        table(
            ["Tool", "Parameters"],
            [
                ["query_siem_logs",    "target: str, window_min: int"],
                ["query_iam_sessions", "target: str"],
                ["query_threat_intel", "ioc: str"],
            ],
            col_widths=[W*0.4, W*0.6],
        ),
        sp(4),
        table(
            ["Pilot", "Available actions"],
            [
                ["TELECOM",    "block_ip · revoke_session · notify_soc · update_acl"],
                ["INDUSTRY_4", "isolate_plc · revoke_ot_session · notify_soc · update_zt_policy"],
                ["MARITIME",   "block_vessel_access · quarantine_cargo_system · notify_port_authority · notify_soc"],
                ["FINANCE",    "freeze_account · block_transaction · notify_fraud_team · escalate_to_compliance · notify_soc"],
            ],
            col_widths=[W*0.22, W*0.78],
        ),
        sp(6),
    ]

    # C3
    story += [h2("C3 — Action & Policy Execution (mistral-nemo)"), sp(2)]
    story += [
        b("<b>PolicyTranslator</b>: translates natural-language policy_update into OPA/Rego rule using mistral-nemo. "
          "In INTEGRATED mode, Rego rule published to t53.policy_updates for T5.5."),
        b("<b>ActionExecutor</b>: in STANDALONE mode, dispatches each action to the appropriate C4 adapter. "
          "Always passes mode=safe-state for isolate_plc actions."),
        sp(6),
    ]

    # C4
    story += [h2("C4 — Tool Adapter Layer (12 plugins, currently stubs)"), sp(2)]
    story += [
        table(
            ["Pilot", "Plugins", "Actions"],
            [
                ["TELECOM (OTE)",         "SIEMPlugin · IAMPlugin · IDSPlugin",                    "block_ip · revoke_session · notify_soc · update_acl"],
                ["INDUSTRY_4 (Siemens)",  "SIEMPlugin · IAMPlugin · SCADAPlugin",                  "isolate_plc (safe-state enforced) · revoke_ot_session · notify_soc · update_zt_policy"],
                ["MARITIME (Rotterdam)",  "PortSIEMPlugin · PortIAMPlugin · PortOpsPlugin",         "block_vessel_access · quarantine_cargo_system · notify_port_authority · notify_soc"],
                ["FINANCE (CaixaBank)",   "BankSIEMPlugin · BankIAMPlugin · FraudEnginePlugin",     "freeze_account · block_transaction · notify_fraud_team · escalate_to_compliance · notify_soc"],
            ],
            col_widths=[W*0.22, W*0.34, W*0.44],
        ),
        sp(4),
        p("SCADAPlugin enforces safe-state-first: isolate_plc raises ValueError if mode=safe-state is not passed. "
          "C3 always passes it automatically. All adapters are currently simulation stubs — real API calls are planned M10–M15.", "body"),
        sp(6),
    ]

    # C5
    story += [h2("C5 — Safety, Audit & Simulation"), sp(2)]
    story += [
        p("<b>SafetyGate</b> — four rule-based checks before any action executes:", "body"),
        sp(2),
        table(
            ["Check", "Rule", "Fail result"],
            [
                ["1 — Confidence",      "agent_confidence ≥ pilot threshold (0.80 / 0.85 FINANCE)", "ESCALATE"],
                ["2 — Protected IP",    "src_ip not in pilot protected_ranges",                     "ESCALATE"],
                ["3 — Proportionality", "action count ≤ 5",                                         "REJECTED"],
                ["4 — OT scope",        "policy_update must not target full OT network / all zones", "ESCALATE"],
            ],
            col_widths=[W*0.22, W*0.52, W*0.26],
        ),
        sp(4),
        p("ESCALATE cases trigger a semantic second-opinion call to mistral:7b → decides APPROVE or REJECT. "
          "Final verdicts: APPROVED · REJECTED · ESCALATE.", "body"),
        sp(4),
        p("<b>AuditLog</b> — immutable per-event records with pilot-prefixed IDs "
          "(aud-OTE-* · aud-SIE-* · aud-ROT-* · aud-CAI-*). Stores guardrail verdict, all action results, timestamps.", "body"),
        sp(4),
        p("<b>SimulationMode</b> — dry_run (log everything, execute nothing) and digital_twin "
          "(also subscribes to dt.events.synthetic for WP3 D-VISOR synthetic events).", "body"),
        sp(6),
    ]

    # C6
    story += [h2("C6 — Sector Profile Manager"), sp(2)]
    story += [
        p("Loads all four YAML profiles at startup. Each SectorProfile carries: pilot identifier, tool plugin list, "
          "policy templates, LLM system prompt (sector-specific, injected into C2), ot_safety_flag, confidence_threshold, "
          "and protected_ranges. Per-event routing via _profile_for(pilot) and _adapters_for(sector).", "body"),
        sp(6),
    ]

    # ── Pipeline Modes ─────────────────────────────────────────────────────────
    story += [h1("Pipeline Modes"), hr()]

    story += [
        table(
            ["Mode", "Env var", "Flow"],
            [
                ["STANDALONE\n(default)",  "VIGILANCE_MODE=STANDALONE",   "Full C1→C2→C5→C3→C4 inside T5.3. C2 uses Mistral Nemo internally. CanonicalEvent also published to t53.canonical_events for observability."],
                ["INTEGRATED",             "VIGILANCE_MODE=INTEGRATED",   "Two threads, independent pika connections. Thread 1: raw event → C1 → t53.canonical_events → T5.4. Thread 2: t53.action_requests → C5+C3+C4 → t53.policy_updates + t53.actions.dispatch + t53.results."],
                ["DIGITAL_TWIN",           "VIGILANCE_MODE=DIGITAL_TWIN", "Same as STANDALONE plus third consumer on dt.events.synthetic for WP3 D-VISOR injection."],
            ],
            col_widths=[W*0.18, W*0.27, W*0.55],
        ),
        sp(6),
    ]

    # ── Broker Topics ──────────────────────────────────────────────────────────
    story += [h1("Broker Topics (all pre-declared in RabbitMQ)"), hr()]

    story += [
        table(
            ["Topic", "Dir", "Description"],
            [
                ["pilot.events.raw",      "IN",  "Raw events from pilot environments — entry point"],
                ["t53.canonical_events",  "OUT", "C1 output — T5.4 input in INTEGRATED mode; observability in STANDALONE"],
                ["t53.action_requests",   "IN",  "T5.4 output — triggers C5+C3+C4 in INTEGRATED mode"],
                ["t53.policy_updates",    "OUT", "C3 Rego rules → T5.5 ZTA blueprint refinement (fire-and-forget)"],
                ["t53.actions.dispatch",  "OUT", "C4 action requests → pilot tools (fire-and-forget)"],
                ["t53.results",           "OUT", "Final ExecutionResult after every event"],
                ["dt.events.synthetic",   "IN",  "WP3 D-VISOR synthetic events for digital twin mode"],
            ],
            col_widths=[W*0.30, W*0.08, W*0.62],
        ),
        sp(6),
    ]

    # ── REST API ───────────────────────────────────────────────────────────────
    story += [h1("REST API — T5.6 Integration Point (port 8000)"), hr()]

    story += [
        table(
            ["Method", "Endpoint", "Description"],
            [
                ["GET",  "/api/v1/health",           "Liveness check — returns loaded pilots and mode"],
                ["GET",  "/api/v1/profiles",          "All four sector profiles with thresholds and plugin lists"],
                ["POST", "/api/v1/events",            "Submit raw event — returns ExecutionResult (STANDALONE) or 202 (INTEGRATED)"],
                ["POST", "/api/v1/action-requests",   "Submit ActionRequest for C5+C3+C4 execution"],
                ["GET",  "/api/docs",                 "Swagger UI (interactive)"],
                ["GET",  "/api/redoc",                "ReDoc documentation"],
                ["GET",  "/api/openapi.json",         "OpenAPI 3.1 spec"],
            ],
            col_widths=[W*0.10, W*0.35, W*0.55],
        ),
        sp(6),
    ]

    # ── LLM Usage ──────────────────────────────────────────────────────────────
    story += [h1("LLM Usage"), hr()]

    story += [
        table(
            ["Model", "Component", "When", "What it does"],
            [
                ["mistral:7b",   "C1 LLMParser",       "Unknown log format",      "Extracts all CanonicalEvent fields from free-text"],
                ["mistral:7b",   "C5 SafetyGate",       "ESCALATE cases only",     "Semantic second-opinion: APPROVE or REJECT"],
                ["mistral-nemo", "C2 AgentLoop",        "Every event",             "Multi-turn reasoning — tool calls + threat/action decision"],
                ["mistral-nemo", "C3 PolicyTranslator", "When policy_update set",  "NL → OPA/Rego policy rule translation"],
            ],
            col_widths=[W*0.18, W*0.22, W*0.22, W*0.38],
        ),
        sp(4),
        p("Both models served by Ollama (local Docker container). "
          "When OLLAMA_BASE_URL is unset, StubLLMProvider is used automatically — "
          "deterministic responses, all 101 tests pass offline.", "body"),
        sp(6),
    ]

    # ── Infrastructure ─────────────────────────────────────────────────────────
    story += [h1("Infrastructure"), hr()]

    story += [
        table(
            ["Component", "Details"],
            [
                ["RabbitMQ 3.13",    "All 7 queues pre-declared from infra/rabbitmq/definitions.json at startup"],
                ["Ollama",           "Serves mistral:7b (~4 GB) and mistral-nemo (~7 GB) — downloaded once into persistent Docker volume"],
                ["Docker Compose",   "4 services: rabbitmq · ollama · ollama-init (one-shot model downloader) · vigilance-gate"],
                ["vigilance/main.py","Combined entrypoint: REST API (uvicorn, port 8000) in daemon thread + broker consumer(s) in main thread"],
            ],
            col_widths=[W*0.25, W*0.75],
        ),
        sp(6),
    ]

    # ── Developer Tools ────────────────────────────────────────────────────────
    story += [h1("Developer Tools"), hr()]

    story += [
        table(
            ["Tool", "Description"],
            [
                ["tools/publish_event.sh",  "Sends any raw event to pilot.events.raw via RabbitMQ Management API. Supports CEF, JSON, syslog for all 4 pilots."],
                ["tools/simulate_t54.sh",   "Simulates T5.4: auto-consumes a CanonicalEvent, derives sector-appropriate actions, publishes ActionRequest to t53.action_requests."],
            ],
            col_widths=[W*0.30, W*0.70],
        ),
        sp(6),
    ]

    # ── Tests ──────────────────────────────────────────────────────────────────
    story += [h1("Test Suite — 101 Tests, All Passing (offline)"), hr()]

    story += [
        table(
            ["Suite", "Tests"],
            [
                ["test_c1_ingestion.py",          "All 5 parsers + normalizer"],
                ["test_c2_agentic.py",             "AgentLoop tool calls, final decision, fallback"],
                ["test_c3_execution.py",           "ActionExecutor, PolicyTranslator, unknown action"],
                ["test_c4_adapters.py",            "All 12 plugins including SCADA safe-state enforcement"],
                ["test_c5_safety.py",              "SafetyGate verdicts, AuditLog, SimulationMode"],
                ["test_c6_profiles.py",            "All 4 profile loads, caching, validation"],
                ["test_api.py",                    "All REST endpoints, 4 pilots, Swagger/ReDoc/OpenAPI"],
                ["tests/scenarios/ (4 files)",     "Full end-to-end: OTE · Siemens · Rotterdam · CaixaBank"],
            ],
            col_widths=[W*0.42, W*0.58],
        ),
        sp(6),
    ]

    # ── Not Yet Implemented ────────────────────────────────────────────────────
    story += [h1("Not Yet Implemented — Planned M7–M18"), hr()]

    story += [
        table(
            ["Item", "Current state", "Planned"],
            [
                ["Real C4 adapters (live tool APIs)",   "Stubs — simulate responses",      "M10–M15 per pilot"],
                ["T5.1 RAG in C2",                      "Interface not yet wired",         "M10–M12"],
                ["T5.2 agent selection",                "Uses Mistral Nemo directly",       "M13–M15"],
                ["Real T5.4 orchestration",             "Simulated via simulate_t54.sh",    "M12–M13"],
                ["API key authentication",              "Header stub — no enforcement",     "M7–M9"],
                ["Audit REST endpoint",                 "Not yet implemented",              "M7–M9"],
                ["Adaptive confidence thresholds",      "Not yet",                          "M16–M18"],
                ["Long-term memory for C2",             "Not yet",                          "M16–M18"],
            ],
            col_widths=[W*0.38, W*0.30, W*0.32],
            header_bg=ORANGE,
        ),
        sp(6),
    ]

    # ── Footer note ────────────────────────────────────────────────────────────
    story += [
        hr(),
        p(f"Generated {date.today().strftime('%d %B %Y')} — VIGILANCE GAP-101249737 · T5.3 Lead: INNOV · "
          "Repository: mtouloup/vigilance-GATE · Branch: claude/setup-vigilance-t5-3-7HVrt", "caption"),
    ]

    doc.build(story)
    print(f"PDF generated: {OUTPUT}")

if __name__ == "__main__":
    build()

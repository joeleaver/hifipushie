# STATE: mcp-rules -- the MCP server carries the clothing and review rules (2026-10-19)

## Current best (on main, 2026-10-19 integration)
- Tools (server.py): `pattern_check`, `fit_garment`, `alter_pattern` (cloth); `review_view` (core); `judge_asset`
  (export); `game_garment` (export: garment_game's pattern-space game garments, LOD pierce gate). `dress` refuses without a pattern-gate PASS up front (cloth_check.gate_status); `look_cloth` renders the
  diag rows by default (DIAG_DEFAULT: panels+seams+turned; strain+layers); `look` on a character ends with a judge line.
- next_steps.py: every stage tool's "next:" lines, generated from its result.
- INSTRUCTIONS + cloth guide (intro, order, stages table, rule 3, craft rules, self-review) + guide_spec: the order
  pattern -> pattern_check -> fit_garment -> judge clay + diag (one review_view per view) -> optional sim (wrinkles)
  -> game mesh. Topics "traps", "gates", "tailoring" (repo docs).
- Audit table: docs/notes/mcp_audit.md. Codified M1-M8, M13 (C4 superseded).

## Decisions in force
- Tools refuse what the gates forbid (dress, fit_garment before a PASS); `force` never bypasses the pattern gate (the
  logged env override HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE stays the only way).
- Diag is on by default in garment looks; diag=False turns it off.
- review_view takes ONE region / pair per call; dry=True hands back the pair + prompt for a fresh agent.
- Next-step lines are short and built from the result (rows, strain p99, pierce, verdict), never fixed boilerplate.
- One dress-form switch everywhere: cloth_check.form_validated() (gate, fit_garment, next_steps).

## Open
1. Wired on landing (mcp_audit.md "Wired when the branches landed"); run the render test under capped once.
2. game_garment on ag_garrett2 (frozen_ae drapes, rest, no poses; mcp_tool/run.log, 25 s) REFUSES: shirt through
   jacket 0 / 2 / 11 / 17 faces at LOD0-3 (proof6g 0 / 0 / 4 / 39 with its pose-set body + jacket-only gap) and 3
   uncovered pattern-outline edges on the shirt at LOD1-3 (proof6g had 2 / 0 / 3 / 3, never gated). The bake path
   (bake=True on a clean set) has not run through the tool yet: it waits on garment_game STATE fault 2 + the cracks.
3. bin/review-ab not exposed (judge ab is the validated A/B).
4. The running MCP server has the old code until restarted.

## Commands
- Light: `HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates /mnt/data/hifipushie/bin/slot uv run pytest tests/test_mcp_rules.py`
- Renders: `... CAP=8G /mnt/data/hifipushie/bin/capped uv run pytest tests/test_mcp_rules.py -k render`
- Test model: /mnt/data/hifipushie/mcp_rules/ws (model "t": MakeHuman base + A-line skirt; renders in _looks/t).

## History
docs/notes/mcp_audit.md "## History".

STATE: landed on main with the dress form / tailoring / validation branches, wiring done. NEXT: restart the MCP; render test.

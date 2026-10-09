# MCP tool definitions: toolsets and short descriptions (2026-10-09, "toolsets" agent)

The user: the server's tool definitions cost ~36k tokens on every turn (75 tools) plus 2.8k of instructions.

## What changed
- **Short descriptions.** Every tool's docstring (= its MCP description) is now what it does, its key parameters
  and when to use it, ending `Details: guide(topic="<tool>")`. The old full text moved VERBATIM into the guide
  topics, as a `## Tool reference` section at the end of each domain guide with one `### \`tool\`` section per tool
  (plus the tool's signature with defaults): core/plan/scene/export tools in the new `tools_guide.md`
  (topic "tools", which also has the toolset table), the others in hair/cloth/cloth_reference/human/skin/likeness/
  terrain/vegetation/clutter guides. `guide(topic=<tool name>)` returns one section (`server._tool_section`);
  domain topics win over tool names (`guide("human")`, `guide("skin")` return the whole guide, which ends with the
  section).
- **Instructions.** `server.INSTRUCTIONS` is ~450 tokens; the old 2.8k text is verbatim in guide.md, section
  "Overview: the spec format and the tools".
- **Compact schemas.** `_compact_schema` drops pydantic's per-field `title`s and `additionalProperties: true`, and
  advertises `X | None = None` as plain X (only the advertised schema; validation still uses the function's model,
  so an explicit null is still accepted). About a third of the schema text.
- **Toolsets.** `server.TOOLSETS` (each tool in exactly one): core (guide, enable_toolset, list_models, get_model,
  kit_reference, put_model, edit_model, look, check, measure, history, revert), plan, scene, export, human, likeness,
  hair (+scene), cloth (+scene), terrain, plants, clutter. The decorator (`_tool_with_errors`) only records each
  tool in `_TOOLS`; `_register_toolsets()` at the end of the module registers core + `HIFIPUSHIE_TOOLSETS`
  (default `core`; `all`; or `hair,cloth`). `enable_toolset(name)` registers more at run time and notifies
  both ways: `ctx.notify_tools_changed()` (the SubscriptionBus: 2026-07-28-era clients get it on their
  `subscriptions/listen` stream) and `ctx.session.send_tool_list_changed()` (legacy-era clients; the SDK drops it
  at the modern era). `create_initialization_options` is wrapped so legacy-era handshakes advertise
  `tools.listChanged`. `HIFIPUSHIE_CALL_TOOL=1` adds `call_tool(name, args)` (runs any tool). Tools defined after
  start-up (tests/artist_test_tools.py) register at once (`_STARTED`).
- The oxidegen artist and its worker call `server.enable_all()`: a department session gets every capability;
  enable_toolset / call_tool are excluded there.

## Numbers (chars/4 of the tools/list JSON; /mnt/data/hifipushie/toolsets/measure.py)
| mode | tools | tool defs | instructions | total |
|---|---|---|---|---|
| before | 75 | 36,064 | 2,800 | 38,864 |
| all (HIFIPUSHIE_TOOLSETS=all) | 76 | 11,198 | 452 | 11,650 |
| core (default) | 12 | 1,477 | 452 | 1,929 |
| core + hair (+scene) | 20 | 2,593 | 452 | 3,045 |
Descriptions alone went 24.3k -> 4.6k; schemas 11.7k -> 6.6k.

## Does Claude Code pick up list_changed? Yes (2.1.295, headless, tested)
`claude -p` with HIFIPUSHIE_TOOLSETS=core: enable_toolset("terrain"), then ToolSearch found the new
mcp__hp__terrain_history (it arrives deferred) and the call worked, in the same turn. The first attempt failed:
Claude Code negotiates the modern protocol (2026-07-28: "protocolEra modern", via server/discover) where the plain
session notification is dropped; publishing on the SubscriptionBus fixed it. Debug log: ~/.claude/debug/*.txt.
Note also in that log: the stdio handshake spends ~6 s on a version-negotiation probe timeout before connecting.

## Tests
tests/test_toolsets.py: every tool in one toolset and the union = the 75 + enable_toolset; default = core; `all`
over stdio lists all 76; enable over stdio adds hair + scene and the client sees the list_changed notification;
call_tool fallback; every description short, pointing at its section when the section has more, and every
parameter named in the description or the section; compact schema. The verbatim check of every old description
against its section (and of the old instructions in guide.md) is /mnt/data/hifipushie/toolsets/verify.py with
before.json (the pre-change tools/list).

## Adding a tool
Put it in a TOOLSETS entry (the test fails otherwise; at run time a tool in no set is registered anyway, so it
is never silently lost), give it a short docstring, and its full text as a
`### \`name\`` section under the domain guide's `## Tool reference`.

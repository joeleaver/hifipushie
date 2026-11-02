# Test suite gate

**Gate:** `bin/suite` (fast tier), `bin/suite --full` (all). Exit 0 = nothing new against tests/known_failures.txt;
1 = new failures; 2 = no verdict (run aborted, malformed list). Never run it inside resources.heavy (it refuses).

**What exists (branch suite-repair):**
- tests/conftest.py: os.environ + cwd restored after every test and module; limits per phase (60 s, slow 900 s,
  `@pytest.mark.timeout(s)`) on time the test had a CPU; faulthandler backstop for hangs in C; `network` skip when
  PyPI is unreachable; assets from the main checkout's workspace/_templates; `HIFIPUSHIE_TEST_CPULOG` logs CPU per phase.
- pyproject: plain pytest deselects `slow`; tests/slow_tests.txt carries the marks (a list, so no churn in test files).
- bin/suite: hermetic HIFIPUSHIE_HOME per run (same answer in any checkout, workspace-model tests skip), under capped.
  `--full` writes /mnt/data/hifipushie/suite_cpu.log; `--recut` rewrites slow_tests.txt from it (cut 3 CPU s).
- Fixtures added for the terrain tests that only ever ran as scripts (fixture 'T' not found: 27 ERROR on main).
- Saved speed patch: test_drape + test_mcp_rules fixture sharing applied; its @slow decorators dropped for the list.
- Fixed: stale lash count, test_blockin's missing need_ref, BUILD 22 golden, CLAUDE.md back under 8 KB (test_codified).

**Measured:** load average 85-150 from other work; the hifipushie slice has CPU weight 20, so jobs got about 8 % of a
core and wall was 12 x CPU. That is why limits discount CPU wait. The sweep reached 51 of 159 files.

**NOT DONE, in order of weight:**
- slow_tests.txt is PROVISIONAL: 107+ unmeasured files sit in it whole, so the fast tier is only ~400 tests until the
  first recut. It is thin, not wrong: everything still runs in --full.
- The fast tier was never seen to finish here; its check ran on after this page: /mnt/data/hifipushie/suite_sweep/fast1.txt
  (last line = exit code and time). Under 10 minutes on a quiet laptop is unproven; est. ~130 CPU s.
- known_failures.txt holds only the two faults from main's baseline, not re-confirmed on integrate. test_artist (7)
  and test_artist_setup (1) failed in the sweep with "no result for": timing under starvation or real, undecided.
  (test_rented_sims: a stale test, fixed on full-green.)

**test_colour_read_and_fit_recover_zones:** no verdict on quiet timing. Not a deadlock: main, 79cbce57^ and 79cbce57 all
ran past 500 s in the slot, main's stack at 240 s was in numpy under paint.cells inside the first Albedo calls, moving.
So 79cbce57 did not start it. Each Albedo call rebuilds paint layers (over 110 CPU s for no finished call on integrate);
the fit makes many. Slow tier, timeout 1800.

**full-green (2026-11-02, from integrate 7ad32ad2):** integrate's full run (33 F / 2 E, 28 new) triaged:
- 17 x KeyError 'nap': test_artist's in-process artist_test_tools tool (and enable_all) leaked into the MCP registry.
  conftest now puts the registry back (server._TOOLS, native tools, _CALL_TOOLS, TOOL_GROUPS) per test and module.
- 12 x KeyError 'n': test_cloth_precache stubbed cloth._build at import (collection), so every later cloth.build was
  the stub. Now a module fixture; conftest restores hifipushie attributes patched with test code at module end and
  REFUSES a run whose test files patch hifipushie at import (UsageError at collection).
- bin/suite read `(\S+)` ids: 6 parametrized failures with spaces in their ids never reached the verdict. Fixed.
- Real, fixed: chain_garment description 790 > 700 chars (83d88e60). Stale tests updated: toolsets list lacked
  set_expression (5ffab5a2); rented-sims test predates the pattern gate (eacfe6c4: gate file + gated= kwarg); diag strip
  KAT predates the past-cap strain map (C235, 04280b99).
- Known (real, open in docs/state/threads_hard.md, same numbers): fold run-off 26.5, sprung fall ripple 16.9,
  two-piece collar fold_on_base 0.107. test_skin budget entry stays.
- The failing tests rerun in order with their leaking neighbours: 86 passed. Full proof run: started 04:26,
  log /mnt/data/hifipushie/suite_sweep/full_green1.log, verdict /mnt/data/hifipushie/suite_sweep/full_green1.txt
  (last line exit code); not read by this run.

NEXT: read suite_sweep/full_green1.txt: exit 0 -> land full-green; anything new -> triage it (leak first: run it with its
neighbours), then `bin/suite --recut`, commit slow_tests.txt, and `bin/suite` on a quiet machine to prove the 10 minutes.

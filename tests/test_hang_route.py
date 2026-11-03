"""The hang's route (zozo_hang.run): a remote route configured on this machine (localconf, never in the repo) runs a
gated chain job there without holding the local heavy / GPU slot; nothing configured, an ungated job, or a route that
answers exit 9 runs here under the slot. The chain job's gate is its own structure PASS + step 7a (chain_gate.json)."""
import contextlib
import os
import stat
import sys

import numpy as np
import pytest

from hifipushie import cloth_job as cj, localconf, resources, zozo_hang as zh


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HIFIPUSHIE_LOCAL_CONF", str(tmp_path / "local.env"))
    monkeypatch.delenv(zh.REMOTE_KEY, raising=False)
    held = []

    @contextlib.contextmanager
    def heavy(*a, **k):
        held.append(k.get("gpu"))
        yield
    monkeypatch.setattr(resources, "heavy", heavy)
    monkeypatch.setattr(cj, "clear_strays", lambda *a, **k: [])

    def local_zozo(jd):  # the local solver, stubbed: writes out.npz
        return [sys.executable, "-c", f"import numpy as np; np.savez({str(jd / 'out.npz')!r}, V=np.ones((3, 3)))"], None
    monkeypatch.setattr(cj, "zozo_command", local_zozo)
    jd = tmp_path / "job"
    jd.mkdir()
    return tmp_path, jd, held


def _route(tmp, code: int, name: str = "lan.sh") -> str:
    s = tmp / name
    s.write_text("#!/bin/sh\n" + (f'python3 -c "import numpy as np, sys; np.savez(sys.argv[1] + \'/out.npz\', V=np.zeros((3, 3)))" "$1"\n'
                                  if code == 0 else "") + f"exit {code}\n")
    s.chmod(s.stat().st_mode | stat.S_IEXEC)
    return str(s)


def test_nothing_configured_runs_here_under_the_slot(env):
    tmp, jd, held = env
    zh.write_chain_gate(jd, "PASS", "step 7a approved")
    out, lines = zh.run(jd, log=lambda m: None)
    assert held == [True] and np.all(out["V"] == 1) and "zozo hang: ran locally" in lines


def test_configured_route_holds_no_local_slot(env):
    tmp, jd, held = env
    (tmp / "local.env").write_text(f"# this machine\n{zh.REMOTE_KEY}={_route(tmp, 0)}\n")
    zh.write_chain_gate(jd, "PASS_WAIVED", "step 7a approved")
    out, lines = zh.run(jd, log=lambda m: None)
    assert held == [] and np.all(out["V"] == 0)
    assert any(m.startswith("zozo hang: ran remotely") for m in lines)


def test_ungated_job_never_goes_remote(env):
    tmp, jd, held = env
    (tmp / "local.env").write_text(f"{zh.REMOTE_KEY}={_route(tmp, 0)}\n")
    zh.write_chain_gate(jd, "FAIL", "step 7a approved")
    assert zh.chain_gate(jd)[0] is False
    out, lines = zh.run(jd, log=lambda m: None)
    assert held == [True] and np.all(out["V"] == 1)
    (jd / zh.CHAIN_GATE).unlink()
    assert zh.chain_gate(jd) == (False, "no chain gate record (structure PASS + step 7a) beside the job")
    assert zh.chain_gate(jd.parent)[0] is False


def test_route_not_available_falls_back_here(env):
    tmp, jd, held = env
    os.environ[zh.REMOTE_KEY] = _route(tmp, 9)  # (the environment wins over the file)
    try:
        zh.write_chain_gate(jd, "PASS", "step 7a approved")
        out, lines = zh.run(jd, log=lambda m: None)
    finally:
        del os.environ[zh.REMOTE_KEY]
    assert held == [True] and "zozo hang: the remote route is not available: ran locally" in lines


def test_route_failure_is_not_hidden(env):
    tmp, jd, held = env
    (tmp / "local.env").write_text(f"{zh.REMOTE_KEY}={_route(tmp, 1)}\n")
    zh.write_chain_gate(jd, "PASS", "step 7a approved")
    with pytest.raises(RuntimeError, match="exit 1"):
        zh.run(jd, log=lambda m: None)
    assert held == []


def test_paid_route_needs_the_opt_in(env, monkeypatch):
    tmp, jd, held = env
    monkeypatch.delenv("HP_SUBMIT_SIMS", raising=False)
    (tmp / "local.env").write_text(f"{zh.REMOTE_KEY}={_route(tmp, 0, 'bundle.sh')}\n")
    zh.write_chain_gate(jd, "PASS", "step 7a approved")
    with pytest.raises(cj.SimNotSubmitted):
        zh.run(jd, log=lambda m: None)
    assert held == [] and not (jd / "out.npz").exists()


def test_localconf_reads_the_file_under_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HIFIPUSHIE_LOCAL_CONF", str(tmp_path / "x.env"))
    monkeypatch.delenv("HP_TEST_A", raising=False)
    assert localconf.get("HP_TEST_A", "d") == "d"
    (tmp_path / "x.env").write_text("HP_TEST_A='file'  # c\n")
    assert localconf.get("HP_TEST_A") == "file" and localconf.environ()["HP_TEST_A"] == "file"
    monkeypatch.setenv("HP_TEST_A", "env")
    assert localconf.get("HP_TEST_A") == "env"

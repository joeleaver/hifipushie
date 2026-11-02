"""The run-budget hook: main session free, agents stopped at the limit, closing moves allowed, broken input harmless."""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "bin" / "hooks" / "agent_budget.py"


def run(payload, state):
    p = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True,
                       env={"AGENT_BUDGET_DIR": str(state)})
    assert p.returncode == 0
    return p.stdout


def call(tool, args, agent="a1"):
    return json.dumps({"agent_id": agent, "tool_name": tool, "tool_input": args})


def test_main_session_passes_and_keeps_no_state(tmp_path):
    assert run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}), tmp_path) == ""
    assert not list(tmp_path.iterdir())


def test_budget_refuses_work_but_allows_closing(tmp_path):
    (tmp_path / "a1.json").write_text(json.dumps({"calls": 100, "start": 9e12, "closing": 0}))
    assert "deny" in run(call("Bash", {"command": "pytest tests"}), tmp_path)
    assert run(call("Bash", {"command": "cd x && git commit -m y"}), tmp_path) == ""
    assert run(call("Write", {"file_path": "/r/docs/state/x.md"}), tmp_path) == ""
    assert "deny" in run(call("Edit", {"file_path": "/r/src/x.py"}), tmp_path)


def test_closing_moves_run_out(tmp_path):
    (tmp_path / "a1.json").write_text(json.dumps({"calls": 100, "start": 9e12, "closing": 20}))
    assert "deny" in run(call("Bash", {"command": "git status"}), tmp_path)


def test_broken_input_lets_the_call_through(tmp_path):
    assert run("not json", tmp_path) == ""

"""The session grader's digest + metrics (spikes/audit/audit.py) on a synthetic transcript. No LLM call.
uv run python tests/test_audit.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spikes", "audit"))
import audit  # noqa: E402


def _row(kind, content, t, **kw):
    o = {"type": kind, "timestamp": f"2026-10-15T10:{t:02d}:00Z", "message": {"role": kind, "content": content}}
    o.update(kw)
    return o


def _transcript(path):
    big = "x" * 300
    rows = [_row("user", "You are the dress-test agent. Do the thing.", 0)]
    calls = [("Bash", {"command": "cd /x && git add -A && git commit -m wip"}, "ok", False),
             ("Bash", {"command": "/mnt/data/hifipushie/bin/review out a=r.png:s.png"}, "MAJOR x\nVERDICT: FAIL", False),
             ("Bash", {"command": "spikes/offload/remote.sh job.py out 20 4 gpu j1"}, "submitted", False),
             ("Bash", {"command": "blender -b s.blend --python r.py"}, "rendered", False),
             ("Bash", {"command": "uv run python broken.py"}, "Traceback: boom", True),
             ("Bash", {"command": "uv run python broken.py"}, "Traceback: boom", True),
             ("Bash", {"command": "cat > a.py <<'EOF'\nimport bpy\nblender -b\nEOF\nsleep 30; ls"}, big, False),
             ("Bash", {"command": "/mnt/data/hifipushie/bin/review out a=r.png:s.png"}, "VERDICT: PASS", False)]
    for k, (name, inp, out, err) in enumerate(calls):
        u = {"input_tokens": 1, "cache_read_input_tokens": 1000 * (k + 1) ** 3, "cache_creation_input_tokens": 0,
             "output_tokens": 10}
        a = _row("assistant", [{"type": "tool_use", "id": f"t{k}", "name": name, "input": inp}], k + 1)
        a["message"]["usage"], a["message"]["id"] = u, f"m{k}"
        rows.append(a)
        rows.append(_row("user", [{"type": "tool_result", "tool_use_id": f"t{k}", "content": out, "is_error": err}],
                         k + 1))
    rows.append({"type": "attachment", "timestamp": "2026-10-15T10:20:00Z",
                 "attachment": {"type": "queued_command", "prompt": "Hand over now.", "origin": {"kind": "coordinator"}}})
    rows.append(_row("assistant", [{"type": "text", "text": "Final: the neckband passes; job is alive."}], 30))
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_digest_and_metrics():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "agent-test123.jsonl")
        _transcript(p)
        M, G = audit.run(p, out=os.path.join(d, "out"), do_grade=False)
        assert G is None
        assert M["role"] == "dress-test"
        assert M["tool_calls"] == 8
        assert M["peak_ctx"] == 512001
        assert M["over_ctx_limit"]
        assert M["review_runs"] == 2 and M["pass"] == 1 and M["fail"] == 1 and M["rounds_to_pass"] == 2
        assert M["remote_submits"] == 1 and M["remote_over_12g"] == ["#3:20GB"]
        assert M["local_blender"] == 1 and M["local_blender_uncapped"] == [4]   # the heredoc's "blender -b" is not run
        assert M["errors"] == 2 and list(M["repeat_fails"].values()) == [2]
        assert M["git_add_all"] == [1] and M["commits"] == 1
        assert M["sleeps"] == 1
        dg = open(os.path.join(d, "out", "digest.txt")).read()
        assert "== BRIEF ==" in dg and "Do the thing." in dg
        assert "<< COORDINATOR" in dg and "Hand over now." in dg
        assert "context passed 500k" in dg
        assert "<<EOF [2 lines]" in dg and "import bpy" not in dg
        assert dg.rstrip().endswith("Final: the neckband passes; job is alive.")


if __name__ == "__main__":
    test_digest_and_metrics()
    print("ok")

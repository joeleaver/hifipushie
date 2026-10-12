"""setup.py: the tesshair5 shell scripts retargeted to this worktree, into /mnt/data/hifipushie/tesshair6/ and
spikes/tesshair6/ (copies), plus T56's style / look / the six riff styles as the start."""
import shutil
from pathlib import Path

W = Path(__file__).resolve().parents[2]
S = Path("/mnt/data/hifipushie/tesshair5")
D = Path("/mnt/data/hifipushie/tesshair6")
for d in ("out", "styles", "looks", "grooms"):
    (D / d).mkdir(parents=True, exist_ok=True)
for f in ("run.sh", "go.sh", "cu.sh", "cy.sh", "riffs.sh", "tests.sh"):
    t = (S / f).read_text()
    t = t.replace("/home/joe/dev/hifipushie/.claude/worktrees/agent-a3e04a545de405a3f", str(W))
    t = t.replace("hifipushie/tesshair5", "hifipushie/tesshair6")
    t = t.replace("for d in tesshair5", "for d in tesshair6 tesshair5")
    t = t.replace("$W/spikes/tesshair5:", "$W/spikes/tesshair6:$W/spikes/tesshair5:")
    t = t.replace("riff5.py", "riff6.py")
    (D / f).write_text(t)
    (D / f).chmod(0o755)
    shutil.copy(D / f, W / "spikes/tesshair6" / f)
for f in list((S / "styles").glob("S?.json")) + [S / "styles/T56.json"]:
    shutil.copy(f, D / "styles" / f.name)
shutil.copy(S / "looks/T56.json", D / "looks/T56.json")
print("ok", W)

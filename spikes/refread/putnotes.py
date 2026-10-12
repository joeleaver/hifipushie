"""putnotes.py: the refread section of docs/notes/gnm_atlas.md = /mnt/data/hifipushie/refread/notes.md (replaced whole)."""
p = "/home/joe/dev/hifipushie/.claude/worktrees/agent-afe13b70ba89a707e/docs/notes/gnm_atlas.md"
s = open(p).read()
n = open("/mnt/data/hifipushie/refread/notes.md").read().rstrip("\n") + "\n" + open("/mnt/data/hifipushie/refread/notes2.md").read()
i = s.find("\n## refread (")
if i >= 0:
    s = s[:i]
open(p, "w").write(s.rstrip("\n") + "\n\n" + n.rstrip("\n") + "\n")

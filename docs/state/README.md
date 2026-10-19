# docs/state/

STATE pages are the only required reading for a thread; rewrite (don't append) yours at the end of every session;
history goes to docs/notes/<thread>.md, append-only, read only by grep.

- Max 60 lines. Sections: current best (id, path, exact settings) / open faults ranked by game visibility (1 m / 3 m) /
  decisions in force / dead ends (one line each) / commands / history pointers.
- Private / family heads: no details here or anywhere in the repo (one line "paused" at most).

Judging (every thread): `bin/judge shots <glb> --head <approved head>` -> `bin/judge report <new> --ref <old> --head ..`
-> `bin/judge ab <old> <new> <out> --head ..` (self-checks refuse bad runs; docs/notes/judge.md).

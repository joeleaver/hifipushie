"""p_hscore.py: (applied once) spikes/tess/hscore.py renders the model's CURRENT hair (ID pass and beauty in one
hair_look job on its stage) instead of the stage .blend's own hair (stale after any regrow: stage.ensure's key leaves
the hair out, so the file is not rebuilt)."""
from pathlib import Path

p = Path(__file__).resolve().parents[3] / "spikes/tess/hscore.py"
s = p.read_text()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


a0 = s.index("def idmask(frames):")
a1 = s.index("ids = idmask(frames)")
s = s[:a0] + '''def current(frames):
    """Our hair NOW: one hair_look job on the model's stage with the hair of the model's spec as it is on disk today
    (hair.job from the spec in memory): the beauty tiles and the ID pass (hair objects flat red / green, everything
    else black). Returns ({frame: bool mask}, {frame: RGB image}).
    Until tesshair6 the ID pass rendered the stage's .blend in mode "render" and the beauty came from stage.shoot,
    which reads the stage's own spec.json: both kept the hair the stage was BUILT with (stage.ensure's key leaves the
    hair out, so a regrow rebuilt nothing) and scored a model's old hair after every regrow."""
    import tempfile
    from pathlib import Path
    from hifipushie import hair, scene
    spec = store.load(name)
    sn = stage.ensure(os.environ.get("STAGE_MODEL", name))
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    st["hair"] = spec["hair"]
    ids, imgs = {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        idv = [{**f, "out": str(Path(tmp) / f"{f['name']}_id.png")} for f in frames]
        job = {"blend": str(scene.blend_path(sn)), "views": fr, "size": PX, "samples": 24, "hide": [], "flat": False,
               "transparent": True, "lighting": {**LIGHT, "target": fr[0]["center"]}, "eevee": stage.STAGE_EEVEE,
               "mode": "hair_look", "hair": hair.job(sn, st), "clay_views": [], "id_views": idv, "look_engine": "eevee"}
        scene._blender(job, 2400)
        for f, g in zip(fr, idv):
            a = np.asarray(Image.open(g["out"]).convert("RGBA"), float)
            ids[f["name"]] = (a[..., 3] > 127) & (a[..., :3].max(-1) > 60)
            im = Image.open(f["out"])
            if im.mode == "RGBA":
                bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, c)) for c in LIGHT.get("backdrop", [0.86, 0.86, 0.86])) + (255,))
                im = Image.alpha_composite(bg, im)
            imgs[f["name"]] = im.convert("RGB").copy()
    return ids, imgs


''' + s[a1:]
rep('''ids = idmask(frames)
on = stage.shoot(name, frames, LIGHT, size=PX, hair_on=True)
''', '''ids, on = current(frames)
''')
p.write_text(s)
print("ok")

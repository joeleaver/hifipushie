"""spikes/tour/pack_model.py: a stacked model packed for an offload job carries every content-store file its spec names
(a skin stack's layer maps, the projection's albedo), its model folder's side files (skin_projection/report.json: the
fitted lights), extra models (ref / own), and the reference pictures as @refs paths that unpack() makes absolute.
Run: uv run python tests/test_pack_model.py (or pytest)."""
import json, os, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "spikes", "tour"))
import pack_model  # noqa: E402

A, B, C = "5ad662f7d0e01535", "e716ef9728345340", "0123456789abcdef"


def _home():
    h = tempfile.mkdtemp(prefix="hp_pack_")
    os.makedirs(os.path.join(h, "_images")); os.makedirs(os.path.join(h, "_painted"))
    for i in (A, B):
        open(os.path.join(h, "_images", i + ".png"), "wb").write(b"png" + i.encode())
    open(os.path.join(h, "_images", "ffffffffffffffff.png"), "wb").write(b"unused")
    open(os.path.join(h, "_painted", C + ".npz"), "wb").write(b"npz")
    pic = os.path.join(h, "front.jpg"); open(pic, "wb").write(b"jpg")
    spec = {"skin": {"stack": {"layers": [{"name": "pigment", "image": A}]}, "projection": {"albedo": B, "head": "6249f59d9ca4"}},
            "paint": {"x": {"painted": C}}}
    for m, s in (("head_s", spec), ("head", {"base": {}}), ("lights", {"base": {}})):
        d = os.path.join(h, m); os.makedirs(os.path.join(d, "history"))
        json.dump(s, open(os.path.join(d, "spec.json"), "w"))
        open(os.path.join(d, "history", "0001.json"), "w").write("{}")
    json.dump({"views": [{"image": pic}], "cameras": [{}]}, open(os.path.join(h, "head", "human_refs.json"), "w"))
    os.makedirs(os.path.join(h, "lights", "skin_projection"))
    json.dump({"lights": [1]}, open(os.path.join(h, "lights", "skin_projection", "report.json"), "w"))
    open(os.path.join(h, "head_s", "scene.blend"), "wb").write(b"big")
    return h


def test_pack_carries_stack_images_and_side_models():
    h = _home(); job = tempfile.mkdtemp(prefix="hp_job_")
    r = pack_model.pack(["head_s", "head", "lights"], job, home=h)
    ws = os.path.join(job, "ws")
    assert open(os.path.join(job, "model.txt")).read() == "head_s"
    assert r["store_files"] == 3
    for rel in (f"_images/{A}.png", f"_images/{B}.png", f"_painted/{C}.npz"):
        assert os.path.isfile(os.path.join(ws, rel)), rel
    assert not os.path.exists(os.path.join(ws, "_images", "ffffffffffffffff.png"))   # only what the specs name
    assert os.path.isfile(os.path.join(ws, "lights", "skin_projection", "report.json"))
    assert not os.path.exists(os.path.join(ws, "head_s", "history"))
    assert not os.path.exists(os.path.join(ws, "head_s", "scene.blend"))
    rj = json.load(open(os.path.join(ws, "head", "human_refs.json")))
    assert rj["views"][0]["image"] == "@refs/front.jpg"
    assert os.path.isfile(os.path.join(ws, "_refs", "front.jpg"))
    pack_model.unpack(job)
    p = json.load(open(os.path.join(ws, "head", "human_refs.json")))["views"][0]["image"]
    assert os.path.isabs(p) and os.path.isfile(p)


def test_packed_ids_resolve_through_the_image_store():
    """With HIFIPUSHIE_HOME = the job's ws, images.id_path finds the stack's layer maps (what the renderer reads)."""
    h = _home(); job = tempfile.mkdtemp(prefix="hp_job_")
    pack_model.pack(["head_s"], job, home=h)
    from hifipushie import store, images
    old = store.HOME
    try:
        store.HOME = type(old)(os.path.join(job, "ws"))
        assert images.id_path(A).is_file() and images.id_path(B).is_file()
    finally:
        store.HOME = old


if __name__ == "__main__":
    test_pack_carries_stack_images_and_side_models()
    test_packed_ids_resolve_through_the_image_store()
    print("ok")

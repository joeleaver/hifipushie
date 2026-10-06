"""Fetch CC reference pictures into workspace/hair_refs (photos from Wikimedia Commons by file title; game hair-card
models' preview images from Sketchfab's CC-licensed search), with refs.json (source, licence, author)."""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("/home/joe/dev/hifipushie/workspace/hair_refs")
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "hifipushie-research/1.0 (joe.leaver@lbmepublishing.com)"}
PHOTOS = {"ponytail_side": "File:Woman ponytail.jpeg", "ponytail_right": "File:Ponytail facing right.jpg",
          "ponytail_indian": "File:Indian woman in ponytail.jpg", "ponytail_intact": "File:The ponytail still intact.jpg",
          "hair_ecuador": "File:Hair of woman of Ecuador.jpg", "woman_cc0": "File:Woman-g7bcff0094 1920.jpg",
          "ponytail_thai": "File:Young Thai Woman - Bangkok - Thailand (11707112816).jpg",
          "ponytail_cuba": "File:Young Woman in School Uniform - Vinales - Cuba.JPG"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


refs = json.loads((OUT / "refs.json").read_text()) if (OUT / "refs.json").exists() else {}
if "photos" in sys.argv:
    for name, title in PHOTOS.items():
        q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": title, "prop": "imageinfo",
                                    "iiprop": "url|extmetadata", "iiurlwidth": 1400})
        d = json.loads(get("https://commons.wikimedia.org/w/api.php?" + q))
        ii = next(iter(d["query"]["pages"].values()))["imageinfo"][0]
        m = ii.get("extmetadata", {})
        f = OUT / f"{name}.jpg"
        f.write_bytes(get(ii.get("thumburl") or ii["url"]))
        refs[name] = {"file": f.name, "source": ii["descriptionurl"], "licence": m.get("LicenseShortName", {}).get("value"),
                      "author": re.sub("<[^>]+>", "", m.get("Artist", {}).get("value", ""))[:80], "kind": "photo"}
        print(name, refs[name]["licence"], len(f.read_bytes()) // 1024, "kB")
if "cards" in sys.argv:
    for query in ("hair cards", "realtime hair ponytail", "game hair cards female"):
        q = urllib.parse.urlencode({"type": "models", "q": query, "license": "by", "count": 12})
        d = json.loads(get("https://api.sketchfab.com/v3/search?" + q))
        for r in d.get("results", []):
            im = max(r["thumbnails"]["images"], key=lambda i: i["width"])
            print(r["uid"], "|", r["name"][:50], "|", r["user"]["displayName"], "|", r.get("faceCount"), "|", im["width"])
            if r["uid"] in sys.argv:
                name = "cards_" + re.sub(r"[^a-z0-9]+", "_", r["name"].lower())[:30]
                (OUT / f"{name}.jpg").write_bytes(get(im["url"]))
                refs[name] = {"file": f"{name}.jpg", "source": r["viewerUrl"], "licence": "CC BY 4.0",
                              "author": r["user"]["displayName"], "kind": "game hair cards", "faces": r.get("faceCount")}
(OUT / "refs.json").write_text(json.dumps(refs, indent=1))

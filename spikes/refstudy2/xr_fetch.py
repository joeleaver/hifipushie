"""xr_fetch.py <file> ...: fetch files of github.com/shameem4/headSize-gnm (Apache-2.0; XR Blocks' MediaPipe <-> GNM
head fit) into $D2/xr/ (data only: never executed)."""
import os
import sys
import urllib.request

out = os.path.join(os.environ.get("D2", "/mnt/data/hifipushie/refstudy2"), "xr")
os.makedirs(out, exist_ok=True)
for f in sys.argv[1:]:
    dst = os.path.join(out, f.replace("/", "_"))
    req = urllib.request.Request("https://raw.githubusercontent.com/shameem4/headSize-gnm/HEAD/" + f, headers={"User-Agent": "hifipushie"})
    open(dst, "wb").write(urllib.request.urlopen(req, timeout=60).read())
    print(dst, os.path.getsize(dst))

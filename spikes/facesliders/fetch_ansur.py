"""fetch_ansur.py <dir>: ANSUR II public CSVs (US Army 2012 anthropometric survey; a US government work, public
domain; via Penn State's Open Design Lab, https://www.openlab.psu.edu/ansur2/), male and female, with sha256."""
import hashlib
import sys
import urllib.request
from pathlib import Path

d = Path(sys.argv[1])
d.mkdir(parents=True, exist_ok=True)
for sex in ("MALE", "FEMALE"):
    url = f"https://tools.openlab.psu.edu/publicData/ANSUR_II_{sex}_Public.csv"
    try:
        data = urllib.request.urlopen(url, timeout=120).read()
    except Exception:  # noqa: BLE001
        url = url.replace("https://", "http://")
        data = urllib.request.urlopen(url, timeout=120).read()
    (d / f"ANSUR_II_{sex}_Public.csv").write_bytes(data)
    print(sex, url, len(data), hashlib.sha256(data).hexdigest())

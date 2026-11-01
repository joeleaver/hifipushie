#!/bin/bash
# fetch.sh: download the ground-truth scans into $HIFIPUSHIE_GROUNDTRUTH (default /mnt/data/hifipushie/groundtruth) and
# check them against sources.json's sha256. ~4.3 GB. Licences: CC BY 3.0 (Lee Perry-Smith head), CC BY 4.0 (HSRD-100):
# read sources.json first. Each archive is unpacked into its own directory; nothing in them is executed.
set -e
R=${HIFIPUSHIE_GROUNDTRUTH:-/mnt/data/hifipushie/groundtruth}
mkdir -p $R/lps/mcguire/x $R/lps/threejs $R/hsrd100/dl
cd $R/lps/mcguire
curl -sL --retry 3 -o lpshead.zip https://casual-effects.com/g3d/data10/research/model/lpshead/lpshead.zip
curl -sL -o info.js https://casual-effects.com/g3d/data10/research/model/lpshead/info.js
echo "cc683bb006de4c1770ffbf0ec6da64c02df0173398001013b3782814b6d619ca  lpshead.zip" | sha256sum -c -
unzip -q -o lpshead.zip -d x
curl -sL -o ../threejs/LeePerrySmith_License.txt https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/models/gltf/LeePerrySmith/LeePerrySmith_License.txt
curl -sL -o ../CC-BY-3.0-legalcode.txt https://creativecommons.org/licenses/by/3.0/legalcode.txt
cd $R/hsrd100
curl -sL -o CC-BY-4.0-legalcode.txt https://creativecommons.org/licenses/by/4.0/legalcode.txt
curl -sL -o README_dataset_card.md https://huggingface.co/datasets/digitalrealitylab/HSRD-100/raw/main/README.md
grep -q "license: cc-by-4.0" README_dataset_card.md || { echo "HSRD-100's card no longer says cc-by-4.0: STOP and read it"; exit 1; }
for pp in ${POSES:-HSR0040/HSR0040-Body-023 HSR0112/HSR0112-Body-018}; do
  p=${pp#*/}; B=https://huggingface.co/datasets/digitalrealitylab/HSRD-100/resolve/main/data/$pp
  mkdir -p dl/$p x/$p/photos x/$p/scan
  for f in scans/$p-Scan-LOD0.zip source/$p-RealityCapture.zip source/$p-Photos.zip metadata/pose_meta.json metadata/person_meta.json; do
    curl -sL -C - --retry 5 -o dl/$p/$(basename $f) $B/$f
  done
  (cd dl/$p && sha256sum *.zip *.json > SHA256SUMS)
  unzip -q -o dl/$p/$p-Photos.zip -d x/$p/photos
  unzip -q -o dl/$p/$p-Scan-LOD0.zip -d x/$p/scan
done
echo "fetched; compare dl/*/SHA256SUMS with spikes/groundtruth/sources.json"

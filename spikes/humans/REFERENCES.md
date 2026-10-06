# Growth and proportion references (humans track, 2026-10-05)

The files live in `workspace/skin_refs/ages/` (never in the repo; a copy of this note is its README). Fetched by
`spikes/humans/fetch_refs.sh` and `fetch_snyder.sh`; compiled into `src/hifipushie/growth.json` by
`spikes/humans/make_growth.py`; read by `src/hifipushie/anthro.py`. The compiled table carries medians / means only.

## WHO (who_*.xlsx)
- Child Growth Standards, 0-5 years: length/height-for-age and head circumference-for-age, z-score tables per sex
  (L, M, S per day). https://www.who.int/tools/child-growth-standards/standards
- Growth reference 5-19 years (2007): height-for-age per sex (per month).
  https://www.who.int/tools/growth-reference-data-for-5to19-years
Used: the median M. (WHO measures length lying down under 2 years, standing height after: its own tables step
0.7 cm there.) CDC's growth-chart CSVs (cdc.gov/growthcharts) refuse scripted downloads ("Access Denied"); WHO's and
CDC's medians differ by about a centimetre at these ages.

## Snyder et al. 1977 (snyder1977/*.csv)
"Anthropometry of Infants, Children and Youths to Age 18 for Product Safety Design", UMTRI-77-17, for the US Consumer
Product Safety Commission; the tables as published by NIST "AnthroKids"
(https://math.nist.gov/~SRessler/anthrokids/, data1977/<n>.csv; a US government work). ~4,000 US children.
Per age group (2.0-3.5 ... 17.5-19.0 years; infants 0-2 ... 20-23 months, sexes together): N, mean, s.d., min, 5th,
50th, 95th, max. Files: `<measure>_all|_f|_m.csv`, `infant_<measure>.csv`. What we use: stature, erect sitting
height, HEAD HEIGHT (vertex to menton), head circumference / breadth / length, face height, neck circumference,
shoulder and biacromial breadth, shoulder-elbow and elbow-hand length, hand and foot length, chest / waist / hip
circumference, hip breadth, trochanteric / gluteal furrow / tibiale height; infants: crown-sole, crown-rump, head
circumference, shoulder breadth, hand and foot length.

## What they say (and what artists' charts round it to)
Stature in head heights (WHO stature / Snyder head height; under 2.75 y the head height is estimated from WHO head
circumference x Snyder's ratio of the two at 2.75):

| age | measured | artists' chart (Loomis, "Figure Drawing for All It's Worth", 1943) |
|---|---|---|
| 1 | 4.6 | 4 |
| 3 | 5.4 | 5 |
| 5 | 6.1 | 6 |
| 7 | 6.4 | 6.5 |
| 10 | 7.0 | 7 |
| 13 | 7.6 | 7.25 |
| adult | 8.0 (m 177.1 / 22.1 cm, f 163.0 / 20.3 cm at 17.5-19 y) | 7.5 "normal", 8 "ideal" |

The charts make small children's heads 10-15% bigger than measured children's (a newborn is ~4 heads; a
one-year-old is not). The earlier line-up (sk_21) was judged against chart numbers from memory: by measurement
MakeHuman's head-to-body proportions were right within 2-3% at every age; its SIZES were wrong (60 cm at 1 year, 74
at 3, 149 at 16: it blends baby -> child -> young in straight lines of age) and the grafted head brought an adult's
neck.

Other rules checked against the tables: sitting height is 64% of stature at 1 year, 58% at 3, 54% at 7, 52% adult
(the figure's midpoint moves from the navel to the crotch); biacromial breadth stays ~22-23% of stature, so a
toddler's shoulders (22 cm) are barely wider than its head (14 cm); hands ~11% of stature at every age, feet 15-16%.

## How character artists handle children
- Proportion first: the head count, then the midpoint, then limb lengths (Loomis; Hogarth; Stratz 1909's growth
  diagram, the source of most charts).
- Children are not small adults: a big cranium over a small face (eyes below the head's midline), a short thick
  neck hidden by cheeks and chin from the front, no waist, a belly that leads the profile until 5-6, short legs,
  soft pads over hands and feet.
- Base-mesh tools (MakeHuman, Daz Genesis, Character Creator, MetaHuman) make age a morph of one topology plus a
  uniform scale; none grows a child by scaling an adult. makehuman.py now does the same from measurements: the
  shape by measured maturity (head count), then a scale to the measured median stature.

#!/bin/bash
# growth references -> workspace/skin_refs/ages
D=/home/joe/dev/hifipushie/workspace/skin_refs/ages
mkdir -p $D; cd $D
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
get() { # name url
  curl -sL --max-time 60 -A "$UA" -H "Accept: */*" -H "Accept-Language: en-US" -o "$1" "$2"
  echo "$1: $(file -b "$1" | cut -c1-60) $(stat -c %s "$1")"
}
for f in statage lenageinf hcageinf; do
  get cdc_$f.csv "https://www.cdc.gov/growthcharts/data/zscore/$f.csv"
done
B=https://cdn.who.int/media/docs/default-source/child-growth
get who_hcfa_boys_0_5.xlsx "$B/child-growth-standards/indicators/head-circumference-for-age/expanded-tables/hcfa-boys-zscore-expanded-tables.xlsx"
get who_hcfa_girls_0_5.xlsx "$B/child-growth-standards/indicators/head-circumference-for-age/expanded-tables/hcfa-girls-zscore-expanded-tables.xlsx"
get who_lhfa_boys_0_5.xlsx "$B/child-growth-standards/indicators/length-height-for-age/expandable-tables/lhfa-boys-zscore-expanded-tables.xlsx"
get who_lhfa_girls_0_5.xlsx "$B/child-growth-standards/indicators/length-height-for-age/expandable-tables/lhfa-girls-zscore-expanded-tables.xlsx"
get who_hfa_boys_5_19.xlsx "$B/growth-reference-5-19-years/height-for-age-(5-19-years)/hfa-boys-z-who-2007-exp.xlsx"
get who_hfa_girls_5_19.xlsx "$B/growth-reference-5-19-years/height-for-age-(5-19-years)/hfa-girls-z-who-2007-exp.xlsx"

"""Style sheets: resolve (sheet under the model, model wins) and strip (save keeps only the model's own) round-trip."""
from hifipushie import stylesheet


def test_roundtrip():
    sheet = {"paint": {"skin": {"color": "#aa8877", "roughness": 0.5}, "stubble.L": {"opacity": 0.0, "mask": [1, 2]}},
             "parts": {"body": {"subsurface": 0.3}}, "style": {"look": {"lights": [1]}}}
    model = {"style": {"sheet": "x"}, "paint": {"stubble.L": {"opacity": 0.6}, "shirt": {"color": "#fff"},
                                                "skin": {"roughness": None}},
             "parts": {"body": None}}
    r = stylesheet._merge(sheet, model)
    assert list(r["paint"]) == ["skin", "stubble.L", "shirt"]  # the sheet's layers first
    assert r["paint"]["stubble.L"] == {"opacity": 0.6, "mask": [1, 2]}
    assert r["paint"]["skin"] == {"color": "#aa8877"}  # null deleted the sheet's roughness
    assert "body" not in r["parts"]
    assert r["style"] == {"look": {"lights": [1]}, "sheet": "x"}
    s = stylesheet._strip(r, sheet)
    assert stylesheet._merge(sheet, s) == r
    assert s["paint"]["stubble.L"] == {"opacity": 0.6} and s["parts"] == {"body": None}
    assert stylesheet._strip(sheet, sheet) == {}


def test_real_sheet_loads():
    sh = stylesheet.load("stylised_realist")
    assert "rules" in sh and "paint" in sh["spec"]
    assert stylesheet.resolve({"style": {"sheet": "stylised_realist"}})["paint"]["stubble.L"]["opacity"] == 0.0


if __name__ == "__main__":
    test_roundtrip()
    test_real_sheet_loads()
    print("ok")

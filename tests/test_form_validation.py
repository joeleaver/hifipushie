"""The virtual dress form's validation flag (2026-10-19 virtual fit): pattern_form.VALIDATED must agree with the recorded
check (frozen_ae's pattern on the form vs the simulated drape of the same pattern; /mnt/data/hifipushie/pattern_form/
record.py writes it from val1.py's measures). A flag set without a passing record is a FAIL. Skipped without the record
(workspace data). Run: uv run python tests/test_form_validation.py"""
import json
import os

from hifipushie import pattern_form as pf


def test_validated_flag_matches_record():
    if not os.path.exists(pf.VALIDATION_RECORD):
        print("SKIP: no", pf.VALIDATION_RECORD)
        return
    rec = json.load(open(pf.VALIDATION_RECORD))
    print(f"form validation: {sum(r['pass'] for r in rec['rows'])} of {len(rec['rows'])} rows pass; failing {rec['failing']}")
    assert pf.VALIDATED == bool(rec["validated"]), (pf.VALIDATED, rec["failing"])
    assert pf.form_validated() == bool(rec["validated"])


if __name__ == "__main__":
    test_validated_flag_matches_record()
    print("PASS test_validated_flag_matches_record")

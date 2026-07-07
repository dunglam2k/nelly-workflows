"""Guard that every main-vg input JSON supplies all of the workflow's REQUIRED inputs.

This is the regression test for the failure Dung hit: `main-vg-pn.json` was missing
`exomiser_data` (a required Directory input with no default, added when the Exomiser
step replaced the old LLM ranker), so a run could not even launch. A stale example
JSON silently dropping a newly-required input is exactly the class of bug this catches
-- statically, in milliseconds, without touching the cluster.
"""
import glob
import json
import os

import pytest
import yaml

WF_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CWL = os.path.join(WF_DIR, "main-vg.cwl")
INPUT_JSONS = sorted(glob.glob(os.path.join(WF_DIR, "main-vg*.json")))


def _is_optional(type_val):
    """A CWL input type is optional if it is nullable (`T?`, or a list containing
    'null')."""
    if isinstance(type_val, str):
        return type_val.endswith("?")
    if isinstance(type_val, list):
        return "null" in type_val
    return False


def required_inputs(cwl_path):
    with open(cwl_path) as fh:
        doc = yaml.safe_load(fh)
    required = set()
    for name, spec in (doc.get("inputs") or {}).items():
        if isinstance(spec, dict):
            if "default" in spec:            # has a default -> optional
                continue
            if _is_optional(spec.get("type")):
                continue
            required.add(name)
        else:                                # bare-string shorthand, e.g. "File" / "File?"
            if not _is_optional(spec):
                required.add(name)
    return required


REQUIRED = required_inputs(CWL)


def test_workflow_has_required_inputs():
    # Sanity: the parser found the inputs we know are required (no defaults).
    for name in ("graph", "ref", "reads1", "reads2", "exomiser_data", "slivar_gnomad"):
        assert name in REQUIRED, f"{name} should be a required workflow input"


def test_input_jsons_exist():
    assert INPUT_JSONS, "no main-vg*.json input files found next to main-vg.cwl"


@pytest.mark.parametrize("path", INPUT_JSONS, ids=lambda p: os.path.basename(p))
def test_json_provides_all_required_inputs(path):
    with open(path) as fh:
        provided = json.load(fh)
    missing = sorted(r for r in REQUIRED
                     if provided.get(r) is None)  # absent or explicit null
    assert not missing, (
        f"{os.path.basename(path)} is missing required workflow input(s): {missing}. "
        f"Every required input of main-vg.cwl must be supplied or the run cannot launch."
    )

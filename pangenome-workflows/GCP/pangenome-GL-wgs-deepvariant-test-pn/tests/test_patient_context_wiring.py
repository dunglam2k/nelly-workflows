import json
from pathlib import Path

import yaml


WORKFLOW_DIR = Path(__file__).resolve().parent.parent


def test_canonical_job_template_has_no_patient_specific_hardcoding():
    job = json.loads((WORKFLOW_DIR / "main-vg-pn.json").read_text())

    assert {"sex", "hpo_terms", "sample_sex"}.isdisjoint(job)


def test_workflow_routes_metadata_context_to_both_consumers():
    workflow = yaml.safe_load((WORKFLOW_DIR / "main-vg.cwl").read_text())
    steps = workflow["steps"]

    assert workflow["inputs"]["hpo_terms"]["default"] == ""
    assert (
        steps["phenofrommetadata"]["in"]["fallback_hpo_terms"]
        == "hpo_terms"
    )
    assert steps["phenofrommetadata"]["out"] == [
        "pheno_output",
        "hpo_terms",
        "expansionhunter_sex",
        "exomiser_sex",
    ]
    assert (
        steps["expansionhunter"]["in"]["sex"]
        == "phenofrommetadata/expansionhunter_sex"
    )
    assert (
        steps["exomiser"]["in"]["hpo_terms"]
        == "phenofrommetadata/hpo_terms"
    )
    assert (
        steps["exomiser"]["in"]["sample_sex"]
        == "phenofrommetadata/exomiser_sex"
    )


def test_patient_context_tool_accepts_the_legacy_hpo_fallback():
    tool = yaml.safe_load((WORKFLOW_DIR / "phenofrommetadata.cwl").read_text())

    fallback = tool["inputs"]["fallback_hpo_terms"]
    assert fallback["type"] == "string"
    assert fallback["default"] == ""
    assert fallback["inputBinding"]["position"] == 2


def test_failed_extractor_does_not_dereference_missing_output_files():
    tool = yaml.safe_load((WORKFLOW_DIR / "phenofrommetadata.cwl").read_text())

    for output in tool["outputs"].values():
        expression = output["outputBinding"]["outputEval"]
        assert "self.length === 0" in expression
        assert "runtime.exitCode !== 0" in expression

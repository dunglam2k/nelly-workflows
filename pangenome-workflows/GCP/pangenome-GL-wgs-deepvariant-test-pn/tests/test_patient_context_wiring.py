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

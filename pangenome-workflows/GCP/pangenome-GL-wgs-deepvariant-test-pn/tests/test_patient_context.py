import importlib.util
from pathlib import Path

import pytest


PATIENT_CONTEXT_PY = Path(__file__).resolve().parent.parent / "patient_context.py"
SPEC = importlib.util.spec_from_file_location("patient_context", PATIENT_CONTEXT_PY)
patient_context = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patient_context)
parse_patient_context = patient_context.parse_patient_context
write_outputs = patient_context.write_outputs


def metadata(*phenotypes, gender="male"):
    return {
        "patient": {
            "gender": gender,
            "phenotypes": list(phenotypes),
        }
    }


def phenotype(label, uri=None, *, excluded=False, term_id=None):
    term = {"label": label, "uri": uri}
    if term_id is not None:
        term["id"] = term_id
    return {"phenotype": term, "excluded": excluded}


def test_extracts_genoor_hpo_terms_and_both_sex_vocabularies():
    context = parse_patient_context(
        metadata(
            phenotype("Chorea", "http://purl.obolibrary.org/obo/HP_0002072"),
            phenotype("Dementia", "HP:0000726"),
            phenotype("Incoordination", term_id="HP_0002311"),
            phenotype("Excluded feature", "HP:0000001", excluded=True),
        )
    )

    assert context == {
        "phenotype_labels": "Chorea;Dementia;Incoordination",
        "hpo_terms": "HP:0002072,HP:0000726,HP:0002311",
        "expansionhunter_sex": "male",
        "exomiser_sex": "MALE",
    }


def test_deduplicates_hpo_terms_and_accepts_female_alias():
    context = parse_patient_context(
        metadata(
            phenotype("Ataxia", "https://example.org/term/HP_0001251"),
            phenotype("Ataxia again", "HP:0001251"),
            gender="F",
        )
    )

    assert context["hpo_terms"] == "HP:0001251"
    assert context["expansionhunter_sex"] == "female"
    assert context["exomiser_sex"] == "FEMALE"


@pytest.mark.parametrize("gender", [None, "unknown", "other"])
def test_rejects_sex_that_expansionhunter_cannot_represent(gender):
    document = metadata(phenotype("Chorea", "HP:0002072"), gender=gender)

    with pytest.raises(ValueError, match="gender"):
        parse_patient_context(document)


def test_rejects_metadata_without_an_included_hpo_term():
    document = metadata(
        phenotype("Uncoded symptom"),
        phenotype("Excluded", "HP:0000001", excluded=True),
    )

    with pytest.raises(ValueError, match="no included HPO-coded phenotype"):
        parse_patient_context(document)


def test_writes_files_consumed_by_cwl(tmp_path: Path):
    context = parse_patient_context(
        metadata(phenotype("Dementia", "HP:0000726"))
    )

    write_outputs(context, tmp_path)

    assert (tmp_path / "phenofile.txt").read_text() == "Dementia"
    assert (tmp_path / "hpo_terms.txt").read_text() == "HP:0000726"
    assert (tmp_path / "expansionhunter_sex.txt").read_text() == "male"
    assert (tmp_path / "exomiser_sex.txt").read_text() == "MALE"

"""Extract analysis inputs from a Genoor patient metadata document.

Genoor serializes a patient's sex and selected ontology terms to YAML.  Keeping
the conversion here avoids duplicating patient-specific values in the static CWL
job template and, importantly, keeps ExpansionHunter and Exomiser in agreement.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml


HPO_ID = re.compile(r"(?:^|[/#])HP[:_](\d{7})(?:$|[/?#])", re.IGNORECASE)


def _normalise_hpo_id(value: object) -> str | None:
    """Return a canonical ``HP:nnnnnnn`` identifier when *value* contains one."""

    if not isinstance(value, str):
        return None
    candidate = value.strip()
    direct = re.fullmatch(r"HP[:_](\d{7})", candidate, re.IGNORECASE)
    match = direct or HPO_ID.search(candidate)
    return f"HP:{match.group(1)}" if match else None


def _phenotype_term(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    nested = item.get("phenotype")
    return nested if isinstance(nested, dict) else item


def _parse_hpo_terms(value: str) -> list[str]:
    """Parse and validate a legacy comma/space-separated HPO term list."""

    if not value.strip():
        return []

    hpo_terms: list[str] = []
    invalid: list[str] = []
    for token in re.split(r"[,;\s]+", value.strip()):
        hpo_id = _normalise_hpo_id(token)
        if hpo_id is None:
            invalid.append(token)
        elif hpo_id not in hpo_terms:
            hpo_terms.append(hpo_id)

    if invalid:
        raise ValueError(
            "fallback HPO terms must contain only HP identifiers; invalid "
            f"value(s): {', '.join(invalid)}"
        )
    return hpo_terms


def parse_patient_context(
    document: dict[str, Any], fallback_hpo_terms: str = ""
) -> dict[str, str]:
    """Convert a Genoor metadata mapping to CWL-ready patient context strings."""

    patient = document.get("patient")
    if not isinstance(patient, dict):
        raise ValueError("metadata is missing the 'patient' object")

    raw_sex = patient.get("gender")
    if not isinstance(raw_sex, str):
        raise ValueError("metadata is missing patient.gender")
    sex_key = raw_sex.strip().lower()
    sex_aliases = {
        "male": "male",
        "m": "male",
        "boy": "male",
        "female": "female",
        "f": "female",
        "girl": "female",
    }
    try:
        expansionhunter_sex = sex_aliases[sex_key]
    except KeyError as exc:
        raise ValueError(
            "patient.gender must be male or female for ExpansionHunter; "
            f"got {raw_sex!r}"
        ) from exc

    phenotypes = patient.get("phenotypes")
    if not isinstance(phenotypes, list):
        raise ValueError("metadata is missing patient.phenotypes")

    labels: list[str] = []
    hpo_terms: list[str] = []
    for item in phenotypes:
        if isinstance(item, dict) and item.get("excluded") is True:
            continue
        term = _phenotype_term(item)
        label = term.get("label")
        if isinstance(label, str) and label.strip():
            labels.append(label.strip())

        hpo_id = None
        for key in ("id", "uri"):
            hpo_id = _normalise_hpo_id(term.get(key))
            if hpo_id:
                break
        if hpo_id and hpo_id not in hpo_terms:
            hpo_terms.append(hpo_id)

    # Older Genoor records contain phenotype labels but serialize every ontology
    # URI as null.  Existing workflow jobs already carry the curated Exomiser HPO
    # list, so retain that value as a compatibility fallback.  Never merge it into
    # coded metadata: when Genoor does provide identifiers, it remains the source
    # of truth and a stale job-template value cannot alter the patient's context.
    if not hpo_terms:
        hpo_terms = _parse_hpo_terms(fallback_hpo_terms)
        if not hpo_terms:
            raise ValueError(
                "metadata contains no included HPO-coded phenotype and no "
                "fallback HPO terms were supplied; add ontology identifiers in "
                "Genoor or provide the workflow hpo_terms input"
            )

    return {
        "phenotype_labels": ";".join(labels),
        "hpo_terms": ",".join(hpo_terms),
        "expansionhunter_sex": expansionhunter_sex,
        "exomiser_sex": expansionhunter_sex.upper(),
    }


def write_outputs(context: dict[str, str], output_dir: Path = Path(".")) -> None:
    outputs = {
        "phenofile.txt": context["phenotype_labels"],
        "hpo_terms.txt": context["hpo_terms"],
        "expansionhunter_sex.txt": context["expansionhunter_sex"],
        "exomiser_sex.txt": context["exomiser_sex"],
    }
    for name, value in outputs.items():
        (output_dir / name).write_text(value, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2):
        print(
            "usage: patient_context.py METADATA.yaml [FALLBACK_HPO_TERMS]",
            file=sys.stderr,
        )
        return 2

    try:
        with Path(args[0]).open(encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
        if not isinstance(document, dict):
            raise ValueError("metadata root must be a mapping")
        fallback_hpo_terms = args[1] if len(args) == 2 else ""
        write_outputs(parse_patient_context(document, fallback_hpo_terms))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"patient metadata error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

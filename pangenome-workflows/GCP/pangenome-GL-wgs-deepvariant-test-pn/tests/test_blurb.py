"""Offline tests for the grounded genome-linter (genome-linter-llm/blurb.py).

These exercise the whole grounding pipeline (Exomiser genes/variants + ExpansionHunter
repeat calls -> prompt -> report) on the REAL Tay-Sachs and Huntington outputs from the
cluster runs, trimmed to compact fixtures under tests/fixtures/. No cluster, no GPU and
no LLM are needed: the model call is bypassed with --no-llm, so what is verified is the
evidence assembly that decides whether the true diagnosis is surfaced or buried.

Key expectations captured here (each maps to a real failure mode we hit before):
  * Tay-Sachs   -> HEXA ranks #1, no repeat expansion flagged.
  * Huntington  -> HTT flagged as a pathogenic-range expansion (46 >= 36); ATXN3
                   (20/24, below its 60 threshold) is NOT flagged.
  * An empty Exomiser ranking with no expansion still produces a report (the step must
    never exit non-zero and leave its output Unavailable).
"""
import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
BLURB_PY = os.path.join(os.path.dirname(HERE), "genome-linter-llm", "blurb.py")


def _load_blurb():
    spec = importlib.util.spec_from_file_location("blurb", BLURB_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


blurb = _load_blurb()


def fx(disease, name):
    return os.path.join(FIX, disease, name)


# --- Exomiser gene ranking -------------------------------------------------------

def test_tay_sachs_ranks_hexa_first():
    genes = blurb.read_genes(fx("TS", "exomiser.genes.tsv"), 10)
    assert genes, "expected non-empty Exomiser ranking"
    top = blurb.pick(genes[0], "GENE_SYMBOL", "GENE")
    assert top == "HEXA", f"Tay-Sachs top gene should be HEXA, got {top}"
    combined = float(blurb.pick(genes[0], "EXOMISER_GENE_COMBINED_SCORE", "COMBINED_SCORE"))
    assert combined > 0.9


def test_read_genes_respects_top_n():
    assert len(blurb.read_genes(fx("HD", "exomiser.genes.tsv"), 5)) == 5


def test_variants_link_hexa_to_causal_splice_variant():
    genes = blurb.read_genes(fx("TS", "exomiser.genes.tsv"), 10)
    symbols = [blurb.pick(g, "GENE_SYMBOL", "GENE") for g in genes]
    vmap = blurb.variants_for(fx("TS", "exomiser.variants.tsv"), symbols)
    hexa = vmap.get("HEXA")
    assert hexa, "HEXA should have contributing variant rows"
    ids = " ".join(blurb.pick(v, "ID", "VARIANT", default="") for v in hexa)
    assert "72346234" in ids, "the true Tay-Sachs variant chr15:72346234 should be present"


# --- ExpansionHunter pathogenic-range flagging -----------------------------------

def test_huntington_flags_htt_expansion():
    flags = blurb.read_eh(fx("HD", "eh_repeats.json"))
    by_gene = {f["gene"]: f for f in flags}
    assert "HTT" in by_gene, "Huntington run must flag the HTT repeat expansion"
    htt = by_gene["HTT"]
    assert htt["max_allele"] == 46 and htt["threshold"] == 36
    assert "Huntington" in htt["disease"]


def test_huntington_does_not_flag_normal_atxn3():
    # ATXN3 is genotyped 20/24 (below its SCA3 threshold of 60); a normal-range locus
    # must never be flagged, or every sample would carry a spurious SCA3 call.
    flags = blurb.read_eh(fx("HD", "eh_repeats.json"))
    assert "ATXN3" not in {f["gene"] for f in flags}


def test_tay_sachs_flags_no_expansion():
    # HTT here is 18/18 -- normal. Nothing should be flagged for an SNV disease.
    assert blurb.read_eh(fx("TS", "eh_repeats.json")) == []


def test_read_eh_missing_file_is_empty():
    assert blurb.read_eh("/nonexistent/eh.json") == []
    assert blurb.read_eh("") == []


# --- Prompt construction ----------------------------------------------------------

def test_prompt_leads_with_expansion_for_huntington():
    genes = blurb.read_genes(fx("HD", "exomiser.genes.tsv"), 10)
    vmap = blurb.variants_for(fx("HD", "exomiser.variants.tsv"),
                              [blurb.pick(g, "GENE_SYMBOL", "GENE") for g in genes])
    flags = blurb.read_eh(fx("HD", "eh_repeats.json"))
    prompt = blurb.build_prompt("HP:0002072,HP:0000726", genes, vmap, flags)
    assert "PATHOGENIC" in prompt and "HTT" in prompt
    assert "lead with it" in prompt  # the eh_rule instruction is active


def test_prompt_single_leader_for_tay_sachs():
    # HEXA (0.9893) is far above ABCA7 (0.5567): margin > 0.05 -> NOT a tie, so the
    # model is told it may name the single leading candidate.
    genes = blurb.read_genes(fx("TS", "exomiser.genes.tsv"), 10)
    prompt = blurb.build_prompt("HP:0000726", genes, {}, [])
    assert "single leading candidate" in prompt
    assert "No pathogenic-range repeat expansion" in prompt


# --- End-to-end main(), LLM bypassed ---------------------------------------------

def _run_main(argv, monkeypatch):
    # run_llm must NEVER be reached under --no-llm; make it explode if it is.
    monkeypatch.setattr(blurb, "run_llm",
                        lambda *a, **k: pytest.fail("run_llm must not be called with --no-llm"))
    monkeypatch.setattr(sys, "argv", ["blurb.py"] + argv)
    blurb.main()


def test_main_writes_report_tay_sachs(tmp_path, monkeypatch):
    out = tmp_path / "gl.txt"
    _run_main([
        "--genes", fx("TS", "exomiser.genes.tsv"),
        "--variants", fx("TS", "exomiser.variants.tsv"),
        "--eh-json", fx("TS", "eh_repeats.json"),
        "--phenotype", "Dementia",
        "--no-llm", "--output", str(out),
    ], monkeypatch)
    text = out.read_text()
    assert "1.HEXA" in text                         # HEXA leads the candidate list
    assert "Genome-linter interpretation" in text


def test_main_writes_report_huntington(tmp_path, monkeypatch):
    out = tmp_path / "gl.txt"
    _run_main([
        "--genes", fx("HD", "exomiser.genes.tsv"),
        "--variants", fx("HD", "exomiser.variants.tsv"),
        "--eh-json", fx("HD", "eh_repeats.json"),
        "--phenotype", "Chorea",
        "--no-llm", "--output", str(out),
    ], monkeypatch)
    text = out.read_text()
    assert "HTT" in text and "Huntington disease" in text


def test_main_empty_ranking_still_writes_report(tmp_path, monkeypatch):
    # Regression guard for the "output Unavailable" failure: an empty genes table with
    # no expansion must produce an inconclusive report and exit 0, not kill the step.
    empty = tmp_path / "empty.genes.tsv"
    empty.write_text("#RANK\tID\tGENE_SYMBOL\tEXOMISER_GENE_COMBINED_SCORE\n")
    out = tmp_path / "gl.txt"
    _run_main(["--genes", str(empty), "--no-llm", "--output", str(out)], monkeypatch)
    assert out.exists()
    assert "inconclusive" in out.read_text().lower()


def test_interpret_falls_back_when_llm_raises(monkeypatch):
    # A broken/missing model must not sink the pipeline: interpret() returns the
    # grounded evidence and a note instead of raising.
    monkeypatch.setattr(blurb, "run_llm",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no model")))
    text, note = blurb.interpret("EVIDENCE-BLOCK", "/no/model.gguf", no_llm=False)
    assert text == "EVIDENCE-BLOCK"
    assert "unavailable" in note.lower()

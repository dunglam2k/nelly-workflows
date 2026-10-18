"""Offline tests for the candidate re-ranking in genome-linter-llm/blurb.py.

Exomiser's combined score is a good SNV/indel ranker but it (a) cannot see repeat
expansions at all and (b) does not use the genotype/mode-of-inheritance/ACMG class of
the contributing variants when ordering genes. blurb.rank_candidates() folds both in
with GENERIC, documented rules (see the RANKING RULES block in blurb.py):

  tier 0  pathogenic-range repeat expansion (ExpansionHunter)
  tier 1  biallelic (homozygous / hemizygous / putative compound-het) P/LP variant(s)
          in a recessive-mode gene whose phenotype fits the patient
  tier 2  monoallelic P/LP variant in a dominant-mode gene whose phenotype fits
  tier 3  everything else, in Exomiser order

Nothing here is specific to a gene or a sample: the fixtures are the real cluster
outputs (TS/HD = first runs; TS2/HD2 = the 18 Oct 2026 reruns where Exomiser put a
heterozygous AD hit above the true homozygous recessive diagnosis), and the synthetic
tests exercise each rule on made-up genes.
"""
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
BLURB_PY = os.path.join(os.path.dirname(HERE), "genome-linter-llm", "blurb.py")


def _load_blurb():
    spec = importlib.util.spec_from_file_location("blurb_rank", BLURB_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


blurb = _load_blurb()

TS_FIXTURES = ["TS", "TS2"]
HD_FIXTURES = ["HD", "HD2"]


def fx(disease, name):
    return os.path.join(FIX, disease, name)


def load(disease, top=None):
    genes = blurb.read_genes(fx(disease, "exomiser.genes.tsv"), top)
    vmap = blurb.variants_for(fx(disease, "exomiser.variants.tsv"),
                              [blurb.pick(g, "GENE_SYMBOL", "GENE") for g in genes])
    flags = blurb.read_eh(fx(disease, "eh_repeats.json"))
    return genes, vmap, flags


def ranked_symbols(disease, top=None):
    genes, vmap, flags = load(disease, top)
    return [c["gene"] for c in blurb.rank_candidates(genes, vmap, flags)]


# --- Real fixtures: the two failure modes from the 18 Oct 2026 review -----------------

@pytest.mark.parametrize("disease", TS_FIXTURES)
def test_tay_sachs_puts_hexa_first(disease):
    # TS2 is the run where Exomiser ranked SEMA6B (het, AD, LP) above HEXA (hom, AR, P).
    symbols = ranked_symbols(disease)
    assert symbols[0] == "HEXA", symbols[:5]


def test_tay_sachs_rerun_exomiser_had_hexa_second():
    # Guard that TS2 really is the problematic case, so the test above is not vacuous.
    genes = blurb.read_genes(fx("TS2", "exomiser.genes.tsv"), 10)
    assert blurb.pick(genes[0], "GENE_SYMBOL") != "HEXA"
    assert blurb.pick(genes[1], "GENE_SYMBOL") == "HEXA"


def test_tay_sachs_rerun_hexa_basis_is_biallelic_recessive():
    genes, vmap, flags = load("TS2")
    top = blurb.rank_candidates(genes, vmap, flags)[0]
    assert top["kind"] == "gene" and top["tier"] == blurb.TIER_BIALLELIC_RECESSIVE
    assert top["zygosity"] == "homozygous" and top["acmg"] == "PATHOGENIC"
    assert "recessive" in top["basis"]


@pytest.mark.parametrize("disease", HD_FIXTURES)
def test_huntington_puts_htt_expansion_first(disease):
    genes, vmap, flags = load(disease)
    ranked = blurb.rank_candidates(genes, vmap, flags)
    assert ranked[0]["gene"] == "HTT"
    assert ranked[0]["kind"] == "repeat_expansion"
    assert ranked[0]["tier"] == blurb.TIER_REPEAT_EXPANSION
    # the SNV/indel genes are still all there, after the expansion
    assert {c["gene"] for c in ranked[1:]} >= {"SEMA6B", "PKD1"}


@pytest.mark.parametrize("disease", TS_FIXTURES)
def test_tay_sachs_has_no_expansion_candidate(disease):
    genes, vmap, flags = load(disease)
    assert all(c["kind"] == "gene" for c in blurb.rank_candidates(genes, vmap, flags))


def test_top_n_is_applied_after_reranking():
    # Re-ranking must see the whole Exomiser table and only then cut to --top, so a
    # promoted candidate is never dropped merely because Exomiser had it below the cut.
    genes, vmap, flags = load("HD2")
    ranked = blurb.rank_candidates(genes, vmap, flags, top_n=3)
    assert len(ranked) == 3 and ranked[0]["gene"] == "HTT"


# --- Generic rules on synthetic rows --------------------------------------------------

def gene_row(sym, moi, combined, pheno, human):
    return {"GENE_SYMBOL": sym, "ID": "%s_%s" % (sym, moi), "MOI": moi,
            "EXOMISER_GENE_COMBINED_SCORE": "%.4f" % combined,
            "EXOMISER_GENE_PHENO_SCORE": "%.4f" % pheno,
            "HUMAN_PHENO_SCORE": "%.4f" % human}


def var_row(sym, moi, start, gt, acmg, contributing="1"):
    return {"GENE_SYMBOL": sym, "ID": "1-%d-A-T_%s" % (start, moi), "MOI": moi,
            "CONTIG": "1", "START": str(start), "GENOTYPE": gt,
            "EXOMISER_ACMG_CLASSIFICATION": acmg, "CONTRIBUTING_VARIANT": contributing}


def rank(genes, variants, flags=()):
    vmap = {}
    for v in variants:
        vmap.setdefault(v["GENE_SYMBOL"], []).append(v)
    return blurb.rank_candidates(genes, vmap, list(flags))


def test_homozygous_recessive_plp_outranks_higher_scoring_het_dominant():
    genes = [gene_row("DOMG", "AD", 0.90, 0.70, 0.70), gene_row("RECG", "AR", 0.40, 0.55, 0.40)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 200, "1/1", "PATHOGENIC")]
    out = rank(genes, variants)
    assert [c["gene"] for c in out] == ["RECG", "DOMG"]
    assert out[0]["tier"] == blurb.TIER_BIALLELIC_RECESSIVE
    assert out[1]["tier"] == blurb.TIER_MONOALLELIC_DOMINANT


def test_compound_het_counts_as_biallelic():
    genes = [gene_row("DOMG", "AD", 0.90, 0.70, 0.70), gene_row("RECG", "AR", 0.40, 0.55, 0.40)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 200, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 300, "0/1", "PATHOGENIC")]
    out = rank(genes, variants)
    assert out[0]["gene"] == "RECG" and out[0]["zygosity"] == "compound heterozygous"
    # the weaker of the two alleles defines the pair's class
    assert out[0]["acmg"] == "LIKELY_PATHOGENIC"


def test_single_het_in_recessive_gene_is_a_carrier_not_a_candidate():
    genes = [gene_row("DOMG", "AD", 0.60, 0.70, 0.70), gene_row("RECG", "AR", 0.90, 0.95, 0.95)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 200, "0/1", "PATHOGENIC")]
    out = rank(genes, variants)
    assert [c["gene"] for c in out] == ["DOMG", "RECG"]
    assert out[1]["tier"] == blurb.TIER_OTHER and "carrier" in out[1]["basis"]


def test_two_het_variants_at_same_position_are_not_compound_het():
    genes = [gene_row("RECG", "AR", 0.40, 0.55, 0.40)]
    variants = [var_row("RECG", "AR", 200, "0/1", "PATHOGENIC"),
                var_row("RECG", "AR", 200, "0/1", "PATHOGENIC")]
    assert rank(genes, variants)[0]["tier"] == blurb.TIER_OTHER


def test_hemizygous_x_linked_recessive_is_biallelic_equivalent():
    genes = [gene_row("DOMG", "AD", 0.90, 0.70, 0.70), gene_row("XRG", "XR", 0.40, 0.60, 0.50)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("XRG", "XR", 200, "1", "PATHOGENIC")]
    out = rank(genes, variants)
    assert out[0]["gene"] == "XRG" and out[0]["zygosity"] == "hemizygous"


def test_phased_homozygous_genotype_is_recognised():
    genes = [gene_row("RECG", "AR", 0.40, 0.55, 0.40)]
    variants = [var_row("RECG", "AR", 200, "1|1", "PATHOGENIC")]
    assert rank(genes, variants)[0]["zygosity"] == "homozygous"


def test_biallelic_recessive_without_phenotype_fit_is_not_promoted():
    # Phenotype fit requires a human-disease term match AND an Exomiser phenotype score
    # no worse than its uninformative default; here the gene has mouse/PPI evidence only.
    genes = [gene_row("DOMG", "AD", 0.90, 0.70, 0.70), gene_row("RECG", "AR", 0.40, 0.50, 0.0)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 200, "1/1", "PATHOGENIC")]
    out = rank(genes, variants)
    assert [c["gene"] for c in out] == ["DOMG", "RECG"]
    assert out[1]["tier"] == blurb.TIER_OTHER and "no phenotype" in out[1]["basis"]


def test_weak_human_match_below_exomiser_default_is_not_a_fit():
    genes = [gene_row("DOMG", "AD", 0.90, 0.70, 0.70), gene_row("RECG", "AR", 0.14, 0.35, 0.35)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 200, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 300, "0/1", "LIKELY_PATHOGENIC")]
    assert [c["gene"] for c in rank(genes, variants)] == ["DOMG", "RECG"]


def test_vus_is_never_promoted_even_when_homozygous():
    genes = [gene_row("DOMG", "AD", 0.60, 0.70, 0.70), gene_row("RECG", "AR", 0.90, 0.95, 0.95)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 200, "1/1", "UNCERTAIN_SIGNIFICANCE")]
    out = rank(genes, variants)
    assert [c["gene"] for c in out] == ["DOMG", "RECG"]
    assert out[1]["tier"] == blurb.TIER_OTHER


def test_non_contributing_variants_are_ignored():
    # Exomiser only classifies the variants it used; a non-contributing row must not
    # turn a VUS gene into a P/LP candidate.
    genes = [gene_row("DOMG", "AD", 0.60, 0.70, 0.70), gene_row("RECG", "AR", 0.90, 0.95, 0.95)]
    variants = [var_row("DOMG", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("RECG", "AR", 200, "1/1", "UNCERTAIN_SIGNIFICANCE"),
                var_row("RECG", "AR", 201, "1/1", "PATHOGENIC", contributing="0")]
    assert [c["gene"] for c in rank(genes, variants)] == ["DOMG", "RECG"]


def test_within_tier_pathogenic_beats_likely_pathogenic_then_combined_score():
    genes = [gene_row("A", "AD", 0.90, 0.70, 0.70), gene_row("B", "AD", 0.50, 0.70, 0.70),
             gene_row("C", "AD", 0.70, 0.70, 0.70)]
    variants = [var_row("A", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("B", "AD", 200, "0/1", "PATHOGENIC"),
                var_row("C", "AD", 300, "0/1", "LIKELY_PATHOGENIC")]
    assert [c["gene"] for c in rank(genes, variants)] == ["B", "A", "C"]


def test_tier_other_keeps_exomiser_order():
    genes = [gene_row("A", "AD", 0.90, 0.70, 0.70), gene_row("B", "AR", 0.50, 0.70, 0.70),
             gene_row("C", "AD", 0.30, 0.70, 0.70)]
    variants = [var_row("A", "AD", 100, "0/1", "UNCERTAIN_SIGNIFICANCE"),
                var_row("B", "AR", 200, "0/1", "PATHOGENIC"),      # carrier
                var_row("C", "AD", 300, "0/1", "UNCERTAIN_SIGNIFICANCE")]
    assert [c["gene"] for c in rank(genes, variants)] == ["A", "B", "C"]


def test_moi_falls_back_to_exomiser_id_suffix():
    g = gene_row("RECG", "AR", 0.40, 0.55, 0.40)
    del g["MOI"]
    out = rank([g], [var_row("RECG", "AR", 200, "1/1", "PATHOGENIC")])
    assert out[0]["moi"] == "AR" and out[0]["tier"] == blurb.TIER_BIALLELIC_RECESSIVE


def test_variants_of_other_moi_rows_are_not_mixed_in():
    # Exomiser lists RTEL1_AD and RTEL1_AR separately; the AR row must only see AR
    # variant rows (one het AD row must not make a second "allele").
    genes = [gene_row("G", "AR", 0.40, 0.55, 0.40)]
    variants = [var_row("G", "AR", 200, "0/1", "PATHOGENIC"),
                var_row("G", "AD", 300, "0/1", "PATHOGENIC")]
    assert rank(genes, variants)[0]["tier"] == blurb.TIER_OTHER


def test_expansion_outranks_everything_and_multiple_sort_by_excess():
    genes = [gene_row("RECG", "AR", 0.95, 0.95, 0.95)]
    variants = [var_row("RECG", "AR", 200, "1/1", "PATHOGENIC")]
    flags = [{"gene": "E1", "disease": "d1", "moi": "autosomal dominant", "genotype": "10/40",
              "max_allele": 40, "threshold": 36, "unit": "CAG", "region": "chr1:1-2", "ci": ""},
             {"gene": "E2", "disease": "d2", "moi": "autosomal dominant", "genotype": "10/90",
              "max_allele": 90, "threshold": 50, "unit": "CTG", "region": "chr2:1-2", "ci": ""}]
    out = rank(genes, variants, flags)
    assert [c["gene"] for c in out] == ["E2", "E1", "RECG"]
    assert out[0]["kind"] == "repeat_expansion"


# --- Prompt: the leader instruction is single-valued and never self-contradictory ------

ALL_FIXTURES = TS_FIXTURES + HD_FIXTURES


def prompt_for(disease, phenotype="Dementia;Chorea"):
    genes, vmap, flags = load(disease)
    return blurb.build_prompt(phenotype, genes, vmap, flags)


@pytest.mark.parametrize("disease", ALL_FIXTURES)
def test_prompt_never_combines_expansion_lead_rule_with_single_leader(disease):
    p = prompt_for(disease)
    assert not (blurb.EH_LEAD_MARKER in p and blurb.SINGLE_LEADER_MARKER in p), p


@pytest.mark.parametrize("disease", HD_FIXTURES)
def test_huntington_prompt_leads_with_expansion_and_forbids_snv_leader(disease):
    p = prompt_for(disease)
    assert blurb.EH_LEAD_MARKER in p
    assert blurb.SINGLE_LEADER_MARKER not in p
    assert "lead with it" in p
    # the expansion is candidate 1 in the evidence block, not a side note
    assert "1. HTT" in p


@pytest.mark.parametrize("disease", TS_FIXTURES)
def test_tay_sachs_prompt_names_hexa_as_single_leader(disease):
    p = prompt_for(disease, "Developmental regression;Hypotonia;Hyperacusis")
    assert blurb.EH_LEAD_MARKER not in p
    assert blurb.SINGLE_LEADER_MARKER in p and "HEXA" in p
    assert "1. HEXA" in p


def test_prompt_no_longer_tells_model_to_rank_by_exomiser_score_alone():
    # The old rule contradicted the EH rule; ordering is now the pipeline's ranking.
    p = prompt_for("HD2")
    assert "rank ONLY by Exomiser" not in p
    assert "do not reorder" in p.lower()


def test_prompt_tie_rule_for_effectively_tied_leaders():
    genes = [gene_row("A", "AD", 0.90, 0.70, 0.70), gene_row("B", "AD", 0.88, 0.70, 0.70)]
    variants = [var_row("A", "AD", 100, "0/1", "LIKELY_PATHOGENIC"),
                var_row("B", "AD", 200, "0/1", "LIKELY_PATHOGENIC")]
    vmap = {"A": [variants[0]], "B": [variants[1]]}
    p = blurb.build_prompt("x", genes, vmap, [])
    assert blurb.TIE_MARKER in p and "A, B" in p
    assert blurb.SINGLE_LEADER_MARKER not in p and blurb.EH_LEAD_MARKER not in p


def test_prompt_leader_markers_are_mutually_exclusive_in_general():
    # Exactly one of the three leader instructions is ever emitted.
    for disease in ALL_FIXTURES:
        p = prompt_for(disease)
        n = sum(m in p for m in (blurb.EH_LEAD_MARKER, blurb.SINGLE_LEADER_MARKER, blurb.TIE_MARKER))
        assert n == 1, (disease, n)


# --- Report ---------------------------------------------------------------------------

def _run_main(argv, monkeypatch):
    monkeypatch.setattr(blurb, "run_llm",
                        lambda *a, **k: pytest.fail("run_llm must not be called with --no-llm"))
    monkeypatch.setattr(sys, "argv", ["blurb.py"] + argv)
    blurb.main()


@pytest.mark.parametrize("disease,first", [("TS", "HEXA"), ("TS2", "HEXA"),
                                           ("HD", "HTT"), ("HD2", "HTT")])
def test_report_candidate_list_starts_with_true_diagnosis(disease, first, tmp_path, monkeypatch):
    out = tmp_path / "gl.txt"
    _run_main(["--genes", fx(disease, "exomiser.genes.tsv"),
               "--variants", fx(disease, "exomiser.variants.tsv"),
               "--eh-json", fx(disease, "eh_repeats.json"),
               "--no-llm", "--output", str(out)], monkeypatch)
    text = out.read_text()
    assert "1.%s" % first in text


# --- Conclusion instruction: decided in code, never a conditional for the model -------

@pytest.mark.parametrize("disease", ALL_FIXTURES)
def test_prompt_with_supported_candidate_forbids_inconclusive(disease):
    p = prompt_for(disease)
    assert blurb.SUPPORTED_MARKER in p
    assert "state that " + blurb.INCONCLUSIVE_MARKER not in p


def test_prompt_conclusion_markers_are_mutually_exclusive():
    genes = [gene_row("A", "AD", 0.90, 0.70, 0.70), gene_row("B", "AD", 0.50, 0.70, 0.70)]
    variants = [var_row("A", "AD", 100, "0/1", "UNCERTAIN_SIGNIFICANCE"),
                var_row("B", "AD", 200, "0/1", "UNCERTAIN_SIGNIFICANCE")]
    ranked = rank(genes, variants)
    assert all(c["tier"] == blurb.TIER_OTHER for c in ranked)
    text = blurb.conclusion_instruction(ranked)
    assert blurb.INCONCLUSIVE_MARKER in text and blurb.SUPPORTED_MARKER not in text
    supported = blurb.conclusion_instruction(
        rank([gene_row("C", "AR", 0.5, 0.7, 0.7)], [var_row("C", "AR", 300, "1/1", "PATHOGENIC")]))
    assert blurb.SUPPORTED_MARKER in supported and "state that" not in supported

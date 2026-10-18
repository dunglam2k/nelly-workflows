#!/usr/bin/env python3
"""Grounded genome-linter: turn Exomiser's ranked output into a readable clinical
interpretation using a LOCAL small LLM (no network / no OpenRouter).

Design: the LLM does NOT rank or recall genes. Exomiser already produced a grounded
ranking from variant rarity + pathogenicity + HPO semantic similarity. This script
feeds the LLM ONLY that evidence (top genes, their scores, and the contributing
variants) and asks it to summarise — so it cannot hallucinate a gene that the
variant evidence does not support (the old failure mode that buried HEXA).

The candidate list the LLM sees is Exomiser's output re-ranked by rank_candidates()
with the generic rules documented in the RANKING RULES block below: pathogenic-range
repeat expansions from ExpansionHunter (which Exomiser cannot score) become first-class
candidates, and the genotype / mode-of-inheritance / ACMG class of the contributing
variants is used to order genes, so that e.g. a homozygous pathogenic variant in a
recessive disease gene is not outranked by a heterozygous likely-pathogenic variant in
an unrelated dominant gene merely because the latter has a slightly better HPO score.
"""
import argparse, csv, json, os, re, sys, textwrap


# Approximate full-penetrance pathogenic repeat-count thresholds (max allele >= value
# => flag) for the clinically actionable ExpansionHunter loci, with disease + typical
# inheritance. Exomiser CANNOT score these (a repeat expansion reaches the VCF only as
# an unscorable symbolic <STR> allele), so a true repeat-expansion diagnosis like
# Huntington is invisible to the variant ranker -- it must be surfaced from EH directly.
# Keyed by ExpansionHunter VariantId/LocusId (gene symbol).
EH_PATHO_THRESHOLDS = {
    "HTT": (36, "Huntington disease", "autosomal dominant"),
    "ATXN1": (39, "Spinocerebellar ataxia type 1 (SCA1)", "autosomal dominant"),
    "ATXN2": (33, "Spinocerebellar ataxia type 2 (SCA2)", "autosomal dominant"),
    "ATXN3": (60, "Spinocerebellar ataxia type 3 / Machado-Joseph (SCA3)", "autosomal dominant"),
    "ATXN7": (37, "Spinocerebellar ataxia type 7 (SCA7)", "autosomal dominant"),
    "CACNA1A": (20, "Spinocerebellar ataxia type 6 (SCA6)", "autosomal dominant"),
    "ATXN8OS": (80, "Spinocerebellar ataxia type 8 (SCA8)", "autosomal dominant"),
    "ATXN10": (800, "Spinocerebellar ataxia type 10 (SCA10)", "autosomal dominant"),
    "TBP": (49, "Spinocerebellar ataxia type 17 (SCA17)", "autosomal dominant"),
    "PPP2R2B": (51, "Spinocerebellar ataxia type 12 (SCA12)", "autosomal dominant"),
    "ATN1": (48, "Dentatorubral-pallidoluysian atrophy (DRPLA)", "autosomal dominant"),
    "AR": (38, "Spinal and bulbar muscular atrophy (Kennedy disease)", "X-linked recessive"),
    "FXN": (66, "Friedreich ataxia", "autosomal recessive"),
    "FMR1": (200, "Fragile X syndrome (full mutation)", "X-linked"),
    "DMPK": (50, "Myotonic dystrophy type 1 (DM1)", "autosomal dominant"),
    "CNBP": (75, "Myotonic dystrophy type 2 (DM2)", "autosomal dominant"),
    "C9ORF72": (30, "ALS / frontotemporal dementia (C9orf72)", "autosomal dominant"),
    "CSTB": (30, "Progressive myoclonic epilepsy type 1 (EPM1)", "autosomal recessive"),
    "JPH3": (41, "Huntington disease-like 2 (HDL2)", "autosomal dominant"),
}


def read_eh(path):
    """Parse an ExpansionHunter JSON; return loci whose larger allele reaches the
    pathogenic threshold, as grounded evidence the LLM can cite. Repeat expansions are
    Exomiser's blind spot, so these are first-class candidate diagnoses, not extras."""
    flags = []
    if not path or not os.path.exists(path):
        return flags
    try:
        doc = json.load(open(path))
    except (ValueError, OSError) as e:
        sys.stderr.write("genome-linter-llm: WARN could not read EH json %s: %s\n" % (path, e))
        return flags
    for locus in (doc.get("LocusResults") or {}).values():
        for v in (locus.get("Variants") or {}).values():
            vid = v.get("VariantId") or ""
            thr = EH_PATHO_THRESHOLDS.get(vid)
            if not thr:
                continue
            gt = str(v.get("Genotype") or "")          # e.g. "18/46" or "25"
            alleles = [int(x) for x in gt.split("/") if x.strip().lstrip("-").isdigit()]
            if not alleles:
                continue
            maxa = max(alleles)
            threshold, disease, moi = thr
            if maxa >= threshold:
                flags.append({
                    "gene": vid, "disease": disease, "moi": moi,
                    "genotype": gt, "max_allele": maxa, "threshold": threshold,
                    "unit": v.get("RepeatUnit") or "", "region": v.get("ReferenceRegion") or "",
                    "ci": v.get("GenotypeConfidenceInterval") or "",
                })
    flags.sort(key=lambda f: f["max_allele"] - f["threshold"], reverse=True)
    return flags


def read_genes(path, top_n=None):
    """Exomiser genes TSV -> rows sorted by combined score (top_n=None keeps all).
    The re-ranking in rank_candidates() must see the whole table, so main() reads
    everything and applies --top only after re-ranking."""
    rows = []
    with open(path) as fh:
        r = csv.DictReader((l for l in fh), delimiter="\t")
        # Exomiser headers are prefixed with '#'; normalise.
        r.fieldnames = [(f or "").lstrip("#").strip() for f in (r.fieldnames or [])]
        for row in r:
            rows.append({(k or "").lstrip("#").strip(): v for k, v in row.items()})
    def score(row):
        for k in ("EXOMISER_GENE_COMBINED_SCORE", "COMBINED_SCORE", "ExomiserGeneCombinedScore"):
            if k in row and row[k] not in (None, "", "."):
                try:
                    return float(row[k])
                except ValueError:
                    pass
        return 0.0
    rows.sort(key=score, reverse=True)
    return rows if top_n is None else rows[:top_n]


def pick(row, *names, default=""):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return default


def variants_for(path, symbols):
    """All Exomiser variant rows for the given gene symbols, keyed by symbol. Every row
    is kept (the classification in rank_candidates() needs all contributing variants of
    a gene); the prompt caps what it displays per gene."""
    by_gene = {s: [] for s in symbols}
    if not os.path.exists(path):
        return by_gene
    with open(path) as fh:
        r = csv.DictReader(fh, delimiter="\t")
        r.fieldnames = [(f or "").lstrip("#").strip() for f in (r.fieldnames or [])]
        for row in r:
            row = {(k or "").lstrip("#").strip(): v for k, v in row.items()}
            g = pick(row, "GENE_SYMBOL", "GENE")
            if g in by_gene:
                by_gene[g].append(row)
    return by_gene


# =====================================================================================
# RANKING RULES
# =====================================================================================
# rank_candidates() merges ExpansionHunter pathogenic-range expansions with Exomiser's
# gene table and orders the result by (tier, ACMG class, Exomiser combined score).
# The rules are generic: they look only at the genotype, the mode of inheritance under
# which Exomiser scored the gene, the ACMG class Exomiser assigned to the contributing
# variants, and Exomiser's own phenotype scores. No gene, locus or sample is special.
#
#   tier 0  TIER_REPEAT_EXPANSION   ExpansionHunter repeat expansion in the pathogenic
#           range (EH_PATHO_THRESHOLDS). Exomiser cannot score repeat expansions, so
#           without this rule a true repeat-expansion diagnosis is invisible to the
#           ranking. The thresholds are full-penetrance thresholds, i.e. the expansion
#           is a molecular diagnosis in its own right; the summary states whether the
#           disease fits the phenotype (no ontology is available in this image, and the
#           phenotype reaches this step as labels, so fit is not computed here).
#   tier 1  TIER_BIALLELIC_RECESSIVE  Recessive-mode gene (AR, XR) with a biallelic
#           P/LP genotype -- homozygous, hemizygous, or two distinct heterozygous P/LP
#           contributing variants (putative compound-het; phase is unknown) -- AND a
#           phenotype fit (below). The genotype fully explains a recessive disease and
#           biallelic P/LP hits are rare, so this outranks ...
#   tier 2  TIER_MONOALLELIC_DOMINANT ... a dominant-mode gene (AD, XD, MT) with a
#           heterozygous/any P/LP contributing variant and a phenotype fit. Heterozygous
#           LoF variants in dominant-disease genes are a common incidental finding in
#           any genome (incomplete penetrance, LoF not the disease mechanism), so a
#           phenotype-matching biallelic recessive hit is the better explanation.
#   tier 3  TIER_OTHER              Everything else: VUS/unclassified variants, a single
#           heterozygous P/LP in a recessive gene (carrier), P/LP without phenotype fit.
#           Kept in Exomiser's order -- Exomiser stays the authority wherever the rules
#           above do not speak.
#
# Within tiers 0-2: tier 0 by excess of the larger allele over the threshold; tiers 1-2
# by ACMG class (PATHOGENIC before LIKELY_PATHOGENIC; for a biallelic pair the weaker
# allele counts), then Exomiser combined score, then Exomiser rank.
#
# P/LP means Exomiser's EXOMISER_ACMG_CLASSIFICATION of a CONTRIBUTING variant is
# PATHOGENIC or LIKELY_PATHOGENIC. Exomiser only classifies the variants it used
# (others are NOT_AVAILABLE), and its ACMG assignment already consumes ClinVar, so
# ClinVar is shown as evidence but not re-interpreted here.
#
# Phenotype fit = the gene has a human-disease phenotype match for the patient's terms
# (HUMAN_PHENO_SCORE > 0, so the fit is not purely model-organism or PPI proximity) AND
# Exomiser's gene phenotype score is at least PHENO_FIT_MIN = 0.5, which is the score
# Exomiser gives a gene with no informative phenotype evidence at all; a match scored
# below that is one Exomiser considers worse than knowing nothing. If the TSV lacks the
# HUMAN_PHENO_SCORE column, the phenotype score alone is used.
# =====================================================================================

TIER_REPEAT_EXPANSION = 0
TIER_BIALLELIC_RECESSIVE = 1
TIER_MONOALLELIC_DOMINANT = 2
TIER_OTHER = 3
TIER_LABEL = {
    TIER_REPEAT_EXPANSION: "pathogenic-range repeat expansion",
    TIER_BIALLELIC_RECESSIVE: "biallelic P/LP in recessive-mode gene, phenotype fit",
    TIER_MONOALLELIC_DOMINANT: "monoallelic P/LP in dominant-mode gene, phenotype fit",
    TIER_OTHER: "Exomiser order",
}
PHENO_FIT_MIN = 0.5
RECESSIVE_MOI = {"AR", "XR"}
DOMINANT_MOI = {"AD", "XD", "MT"}
ACMG_STRENGTH = {"PATHOGENIC": 3, "LIKELY_PATHOGENIC": 2, "UNCERTAIN_SIGNIFICANCE": 1}
PLP_MIN_STRENGTH = 2


def _float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def gene_moi(row):
    """Mode of inheritance under which Exomiser scored this gene row: the MOI column, or
    the suffix of Exomiser's ID (e.g. HEXA_AR) when the column is absent."""
    moi = str(pick(row, "MOI", "MODE_OF_INHERITANCE", default="")).strip().upper()
    if not moi:
        m = re.search(r"_([A-Z]{2})$", str(pick(row, "ID", default="")))
        moi = m.group(1) if m else ""
    return moi


def zygosity(gt):
    """'0/1' -> heterozygous, '1/1' or '1|1' -> homozygous, '1' -> hemizygous (haploid
    call), '0/0' -> reference, anything unparseable -> unknown."""
    alleles = [a for a in re.split(r"[/|]", str(gt or "").strip()) if a not in ("", ".")]
    if not alleles:
        return "unknown"
    if all(a == "0" for a in alleles):
        return "reference"
    if len(alleles) == 1:
        return "hemizygous"
    return "homozygous" if len(set(alleles)) == 1 else "heterozygous"


def acmg_class(vrow):
    return str(pick(vrow, "EXOMISER_ACMG_CLASSIFICATION", "ACMG_CLASSIFICATION",
                    default="")).strip().upper()


def is_contributing(vrow):
    return str(pick(vrow, "CONTRIBUTING_VARIANT", default="")).strip().lower() in ("1", "true")


def classify_gene(row, variants):
    """Apply the RANKING RULES to one Exomiser gene row and its variant rows. Returns a
    candidate dict (kind='gene') with tier, basis text, zygosity, acmg, moi, scores."""
    sym = pick(row, "GENE_SYMBOL", "GENE", default="?")
    moi = gene_moi(row)
    # Only rows scored under the same MOI as this gene row (Exomiser lists e.g. RTEL1_AD
    # and RTEL1_AR separately with their own variant sets); rows without MOI are shared.
    mine = [v for v in variants if gene_moi(v) in ("", moi)]
    contributing = [v for v in mine if is_contributing(v)]
    plp = [v for v in contributing if ACMG_STRENGTH.get(acmg_class(v), 0) >= PLP_MIN_STRENGTH]

    pheno = _float(pick(row, "EXOMISER_GENE_PHENO_SCORE", "PHENO_SCORE", default="0"))
    human_raw = pick(row, "HUMAN_PHENO_SCORE", default=None)
    human = _float(human_raw) if human_raw is not None else None
    fit = pheno >= PHENO_FIT_MIN and (human is None or human > 0)

    zyg, acmg, tier, basis = "", "", TIER_OTHER, ""
    if plp:
        hom = [v for v in plp if zygosity(pick(v, "GENOTYPE", default="")) in ("homozygous", "hemizygous")]
        het_sites = {(pick(v, "CONTIG", default=""), pick(v, "START", "POS", default=""))
                     for v in plp if zygosity(pick(v, "GENOTYPE", default="")) == "heterozygous"}
        if hom:
            best = max(hom, key=lambda v: ACMG_STRENGTH.get(acmg_class(v), 0))
            zyg, acmg = zygosity(pick(best, "GENOTYPE", default="")), acmg_class(best)
            biallelic = True
        elif len(het_sites) >= 2:
            zyg = "compound heterozygous"
            # the weaker allele of the pair decides the pair's class
            acmg = min((acmg_class(v) for v in plp
                        if zygosity(pick(v, "GENOTYPE", default="")) == "heterozygous"),
                       key=lambda c: ACMG_STRENGTH.get(c, 0))
            biallelic = True
        else:
            best = max(plp, key=lambda v: ACMG_STRENGTH.get(acmg_class(v), 0))
            zyg, acmg = zygosity(pick(best, "GENOTYPE", default="")), acmg_class(best)
            biallelic = False

        if moi in RECESSIVE_MOI:
            if biallelic and fit:
                tier, basis = TIER_BIALLELIC_RECESSIVE, (
                    "%s %s variant(s) in a recessive-mode (%s) gene with a phenotype match"
                    % (zyg, acmg, moi))
            elif biallelic:
                basis = ("%s %s in a recessive-mode (%s) gene but no phenotype fit "
                         "(Exomiser phenotype evidence below its uninformative default or "
                         "no human-disease term match)" % (zyg, acmg, moi))
            else:
                basis = ("single heterozygous %s variant in a recessive-mode (%s) gene: "
                         "carrier state, not a diagnosis" % (acmg, moi))
        elif moi in DOMINANT_MOI:
            if fit:
                tier, basis = TIER_MONOALLELIC_DOMINANT, (
                    "%s %s variant in a dominant-mode (%s) gene with a phenotype match"
                    % (zyg, acmg, moi))
            else:
                basis = ("%s %s in a dominant-mode (%s) gene but no phenotype fit"
                         % (zyg, acmg, moi))
        else:
            basis = "%s %s variant, mode of inheritance %s" % (zyg, acmg, moi or "unknown")
    else:
        if contributing:
            best = max(contributing, key=lambda v: ACMG_STRENGTH.get(acmg_class(v), 0))
            zyg, acmg = zygosity(pick(best, "GENOTYPE", default="")), acmg_class(best) or "NOT_AVAILABLE"
        basis = "no pathogenic/likely-pathogenic contributing variant (%s)" % (acmg or "unclassified")

    return {
        "kind": "gene", "gene": sym, "tier": tier, "basis": basis,
        "moi": moi, "zygosity": zyg, "acmg": acmg, "fit": fit,
        "combined": _float(pick(row, "EXOMISER_GENE_COMBINED_SCORE", "COMBINED_SCORE", default="0")),
        "pheno": pheno, "human_pheno": human,
        "row": row, "variants": mine,
    }


def expansion_candidate(flag):
    return {
        "kind": "repeat_expansion", "gene": flag["gene"], "tier": TIER_REPEAT_EXPANSION,
        "basis": ("pathogenic-range repeat expansion: larger allele %d >= full-penetrance "
                  "threshold %d (%s, %s); not scoreable by Exomiser"
                  % (flag["max_allele"], flag["threshold"], flag["disease"], flag["moi"])),
        "moi": flag["moi"], "zygosity": "", "acmg": "", "fit": None,
        "combined": 0.0, "pheno": 0.0, "human_pheno": None,
        "excess": flag["max_allele"] - flag["threshold"], "eh": flag,
    }


def rank_candidates(genes, vmap, eh_flags=None, top_n=None):
    """Merge Exomiser gene rows (in Exomiser order) and ExpansionHunter flags into one
    ranked candidate list according to the RANKING RULES above; cut to top_n last."""
    cands = [expansion_candidate(f) for f in (eh_flags or [])]
    for i, g in enumerate(genes):
        c = classify_gene(g, vmap.get(pick(g, "GENE_SYMBOL", "GENE", default="?"), []))
        c["exomiser_rank"] = i
        cands.append(c)

    def key(c):
        if c["kind"] == "repeat_expansion":
            return (c["tier"], -c["excess"], 0.0, 0)
        if c["tier"] == TIER_OTHER:
            return (c["tier"], 0, 0.0, c["exomiser_rank"])
        return (c["tier"], -ACMG_STRENGTH.get(c["acmg"], 0), -c["combined"], c["exomiser_rank"])

    cands.sort(key=key)
    return cands if top_n is None else cands[:top_n]


# Marker phrases of the three mutually exclusive leader instructions. Tests assert that
# a prompt never contains more than one of them (the old prompt could tell the model
# both to lead with a repeat expansion AND that it "may name [an Exomiser gene] as the
# single leading candidate").
EH_LEAD_MARKER = "LEAD WITH THE REPEAT EXPANSION"
SINGLE_LEADER_MARKER = "single leading candidate"
TIE_MARKER = "effectively TIED"
TIE_MARGIN = 0.05
MAX_VARIANTS_SHOWN = 4


def _candidate_lines(i, c):
    lines = []
    if c["kind"] == "repeat_expansion":
        f = c["eh"]
        lines.append("  %d. %s  REPEAT EXPANSION (ExpansionHunter): %s repeat genotype %s units "
                     "(larger allele %d >= pathogenic threshold %d), unit=%s at %s%s -> %s (%s)" % (
                         i, f["gene"], f["unit"] or "repeat", f["genotype"], f["max_allele"],
                         f["threshold"], f["unit"] or "?", f["region"] or "?",
                         (", CI " + f["ci"]) if f["ci"] else "", f["disease"], f["moi"]))
        lines.append("       rank basis: %s" % c["basis"])
        return lines
    g = c["row"]
    comb = pick(g, "EXOMISER_GENE_COMBINED_SCORE", "COMBINED_SCORE", default="?")
    phen = pick(g, "EXOMISER_GENE_PHENO_SCORE", "PHENO_SCORE", default="?")
    var = pick(g, "EXOMISER_GENE_VARIANT_SCORE", "VARIANT_SCORE", default="?")
    hum = pick(g, "HUMAN_PHENO_EVIDENCE", default="")
    lines.append("  %d. %s  combined=%s pheno=%s variant=%s MOI=%s genotype=%s ACMG=%s" %
                 (i, c["gene"], comb, phen, var, c["moi"] or "?", c["zygosity"] or "?",
                  c["acmg"] or "n/a"))
    lines.append("       rank basis: %s" % c["basis"])
    if hum:
        lines.append("       human-phenotype evidence: %s" % hum[:240])
    shown = sorted(c["variants"], key=lambda v: not is_contributing(v))[:MAX_VARIANTS_SHOWN]
    for v in shown:
        eff = pick(v, "VARIANT_EFFECT", "FUNCTIONAL_CLASS")
        path = pick(v, "EXOMISER_VARIANT_SCORE", "VARIANT_SCORE")
        freq = pick(v, "MAX_FREQUENCY", "MAX_FREQ", "FREQUENCY", default="0")
        cs = pick(v, "CLINVAR_PRIMARY_INTERPRETATION", "CLINVAR", default="")
        lines.append("       variant: %s genotype=%s effect=%s hgvs=%s acmg=%s pathScore=%s "
                     "maxFreq=%s clinvar=%s%s" %
                     (pick(v, "ID", "VARIANT", default="?"), pick(v, "GENOTYPE", default="?"),
                      eff, pick(v, "HGVS", default=""), acmg_class(v) or "n/a", path, freq, cs,
                      " [contributing]" if is_contributing(v) else ""))
    return lines


def leader_instruction(ranked):
    """Exactly ONE of three instructions about the leading candidate, derived from the
    re-ranked list, so the prompt can never both demand an expansion-led summary and
    permit a single SNV/indel leader."""
    if not ranked:
        return "- No candidates are listed; state that the result is inconclusive."
    lead = ranked[0]
    if lead["kind"] == "repeat_expansion":
        exp = [c for c in ranked if c["kind"] == "repeat_expansion"]
        names = ", ".join(c["gene"] for c in exp)
        plural = len(exp) > 1
        return (
            "- %s: candidate%s %s %s a PATHOGENIC-RANGE repeat expansion%s. Exomiser cannot "
            "score repeat expansions, so %s absent from Exomiser's own gene scores by "
            "construction, not for lack of evidence. If the disease fits the patient's "
            "phenotype terms it is very likely THE diagnosis and you must lead with it, "
            "citing the gene, the repeat genotype and threshold, and the disease, and state "
            "explicitly whether the phenotype fits. %sDo NOT name any SNV/indel gene as the "
            "leading candidate; cover the SNV/indel candidates afterwards as the differential."
            % (EH_LEAD_MARKER, "s" if plural else "", names, "are" if plural else "is",
               "s" if plural else "", "they are" if plural else "it is",
               ("Present the %d expansions as a differential in the order listed. " % len(exp))
               if plural else ""))
    tied = [c for c in ranked
            if c["tier"] == lead["tier"] and c["acmg"] == lead["acmg"]
            and lead["combined"] - c["combined"] <= TIE_MARGIN]
    if len(tied) > 1:
        return ("- Candidates %s are %s (same rank basis, Exomiser combined scores within "
                "%.2f): present them as a differential, in the order listed, WITHOUT declaring "
                "one of them the single answer."
                % (", ".join(c["gene"] for c in tied), TIE_MARKER, TIE_MARGIN))
    return ("- Candidate 1 (%s) leads the field on the stated rank basis; you may name it as "
            "the %s, then cover the remaining candidates as the differential."
            % (lead["gene"], SINGLE_LEADER_MARKER))


def build_prompt(phenotype, genes, vmap, eh_flags=None, ranked=None):
    ranked = rank_candidates(genes, vmap, eh_flags) if ranked is None else ranked
    lines = []
    lines.append("Patient HPO/phenotype terms: %s" % (phenotype or "(none provided)"))
    lines.append("")
    lines.append("Ranked candidates (pipeline ranking: ExpansionHunter pathogenic-range repeat "
                 "expansions and Exomiser SNV/indel genes, ordered by the rank basis given for "
                 "each candidate -- repeat expansion > biallelic P/LP in a recessive-mode gene "
                 "with phenotype fit > monoallelic P/LP in a dominant-mode gene with phenotype "
                 "fit > remaining genes in Exomiser combined-score order):")
    for i, c in enumerate(ranked, 1):
        lines.extend(_candidate_lines(i, c))
    if not eh_flags:
        lines.append("")
        lines.append("No pathogenic-range repeat expansion was reported by ExpansionHunter.")
    evidence = "\n".join(lines)

    instruction = textwrap.dedent("""
        You are a clinical genomics assistant. Using ONLY the evidence below, write a
        concise interpretation (5-10 sentences).

        Grounding rules (strict):
        - Discuss the candidates in the order listed and do not reorder them: the order is
          the pipeline's ranking. When you explain why a candidate ranks where it does,
          cite its stated rank basis; do not invent reasons of your own.
        %s
        - For each candidate you discuss, cite its scores, its genotype and ACMG class, the
          contributing variant(s) with their predicted effect and coordinates, and the mode
          of inheritance. For a repeat expansion cite the repeat genotype and threshold.
        - Do NOT introduce genes, diseases, or facts not in the evidence, and do NOT use
          outside clinical knowledge to argue for or against a candidate.
        - If there is neither a repeat expansion nor a candidate with a pathogenic or
          likely-pathogenic variant and a phenotype fit, say the result is inconclusive.

        --- EVIDENCE ---
        %s
        --- END EVIDENCE ---

        Interpretation:""").strip() % (leader_instruction(ranked), evidence)
    return instruction


def run_llm(prompt, model_path):
    """Invoke the local GGUF model. Imported lazily so the module (and the whole
    grounding pipeline above) can be imported and tested without llama_cpp / a model
    file present."""
    from llama_cpp import Llama
    llm = Llama(model_path=model_path, n_ctx=8192, n_threads=os.cpu_count(), verbose=False)
    out = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2, max_tokens=600)
    return out["choices"][0]["message"]["content"].strip()


def interpret(prompt, model_path, no_llm=False):
    """Return (interpretation_text, note). Never raises for an LLM problem: this is
    the FINAL step of a ~30 h pipeline, so a missing/broken model must NOT discard
    Exomiser's ranking. On any failure we fall back to the grounded evidence block
    itself so the run still yields a usable, non-empty report."""
    if no_llm:
        return prompt, "LLM skipped (GL_NO_LLM/--no-llm); showing grounded evidence only."
    try:
        return run_llm(prompt, model_path), ""
    except Exception as e:  # model missing, OOM, llama_cpp import failure, ...
        sys.stderr.write("genome-linter-llm: WARN LLM unavailable (%s); "
                         "falling back to grounded evidence.\n" % e)
        return prompt, "LLM unavailable (%s); showing grounded evidence only." % e


def write_report(output, ranked, eh_flags, text, note=""):
    """Always writes a report file. A final interpretation step must never leave the
    pipeline with no output (that is what makes a step's output show as Unavailable).
    `ranked` is the re-ranked candidate list (repeat expansions + Exomiser genes)."""
    with open(output, "w") as fh:
        fh.write("# Genome-linter interpretation (Exomiser + ExpansionHunter grounded)\n\n")
        if note:
            fh.write("_%s_\n\n" % note)
        if eh_flags:
            fh.write("Pathogenic-range repeat expansions (ExpansionHunter): " + "; ".join(
                "%s %s units (>=%d) -> %s" % (f["gene"], f["genotype"], f["threshold"], f["disease"])
                for f in eh_flags) + "\n\n")
        if ranked:
            fh.write("Ranked candidates (repeat expansions and Exomiser genes, re-ranked by "
                     "genotype/MOI/ACMG; see rank basis in the evidence): " + ", ".join(
                         "%d.%s%s" % (i, c["gene"],
                                      " (repeat expansion)" if c["kind"] == "repeat_expansion" else "")
                         for i, c in enumerate(ranked, 1)) + "\n\n")
            exo = [c["gene"] for c in sorted((c for c in ranked if c["kind"] == "gene"),
                                             key=lambda c: c["exomiser_rank"])]
            if exo:
                fh.write("Exomiser combined-score order (SNV/indel only): " + ", ".join(
                    "%d.%s" % (i, g) for i, g in enumerate(exo, 1)) + "\n\n")
        else:
            fh.write("Candidates: none returned.\n\n")
        fh.write(text + "\n")
    sys.stderr.write("genome-linter-llm: wrote %s (%d chars)\n" % (output, len(text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genes", required=True)
    ap.add_argument("--variants", default="")
    ap.add_argument("--phenotype", default=os.environ.get("GL_PHENOTYPE", ""))
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default=os.environ.get("GL_MODEL_PATH", "/model/model.gguf"))
    ap.add_argument("--top", type=int, default=10,
                    help="Number of candidates kept AFTER re-ranking (repeat expansions "
                         "and Exomiser genes together).")
    ap.add_argument("--no-llm", dest="no_llm",
                    default=os.environ.get("GL_NO_LLM", "") not in ("", "0", "false"),
                    action="store_true",
                    help="Skip the local LLM and emit the grounded evidence block only "
                         "(also via GL_NO_LLM=1). Used by tests and as a safe fallback.")
    ap.add_argument("--eh-json", dest="eh_json", default="",
                    help="ExpansionHunter JSON; pathogenic-range expansions are surfaced "
                         "as candidate diagnoses (Exomiser cannot score repeat expansions).")
    a = ap.parse_args()

    # Read the WHOLE Exomiser table: the re-ranking must see every gene before --top is
    # applied, otherwise a promoted candidate below Exomiser's cut would be lost.
    genes = read_genes(a.genes)
    symbols = [pick(g, "GENE_SYMBOL", "GENE", default="?") for g in genes]
    vmap = variants_for(a.variants, symbols) if a.variants else {}
    eh_flags = read_eh(a.eh_json)
    if eh_flags:
        sys.stderr.write("genome-linter-llm: EH pathogenic-range expansions: %s\n" %
                         ", ".join("%s(%d)" % (f["gene"], f["max_allele"]) for f in eh_flags))
    ranked = rank_candidates(genes, vmap, eh_flags, top_n=a.top)
    if ranked:
        sys.stderr.write("genome-linter-llm: ranked candidates: %s\n" % ", ".join(
            "%s[t%d]" % (c["gene"], c["tier"]) for c in ranked))

    # No SNV/indel candidates AND no pathogenic repeat expansion: still emit a report
    # (inconclusive) rather than exit non-zero, which would fail the whole pipeline at
    # its final step and leave the declared output Unavailable.
    if not genes and not eh_flags:
        sys.stderr.write("genome-linter-llm: WARN no Exomiser genes and no EH expansion; "
                         "writing inconclusive report.\n")
        write_report(a.output, ranked, eh_flags,
                     "No candidate genes were returned by Exomiser and no pathogenic-range "
                     "repeat expansion was detected. The result is inconclusive; review the "
                     "upstream VCF and phenotype terms.")
        return

    prompt = build_prompt(a.phenotype, genes, vmap, eh_flags, ranked=ranked)
    text, note = interpret(prompt, a.model, no_llm=a.no_llm)
    write_report(a.output, ranked, eh_flags, text, note)


if __name__ == "__main__":
    main()

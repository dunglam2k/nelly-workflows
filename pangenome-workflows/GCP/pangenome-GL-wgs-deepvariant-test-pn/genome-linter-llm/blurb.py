#!/usr/bin/env python3
"""Grounded genome-linter: turn Exomiser's ranked output into a readable clinical
interpretation using a LOCAL small LLM (no network / no OpenRouter).

Design: the LLM does NOT rank or recall genes. Exomiser already produced a grounded
ranking from variant rarity + pathogenicity + HPO semantic similarity. This script
feeds the LLM ONLY that evidence (top genes, their scores, and the contributing
variants) and asks it to summarise — so it cannot hallucinate a gene that the
variant evidence does not support (the old failure mode that buried HEXA).
"""
import argparse, csv, json, os, sys, textwrap


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


def read_genes(path, top_n):
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
    return rows[:top_n]


def pick(row, *names, default=""):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return default


def variants_for(path, symbols):
    by_gene = {s: [] for s in symbols}
    if not os.path.exists(path):
        return by_gene
    with open(path) as fh:
        r = csv.DictReader(fh, delimiter="\t")
        r.fieldnames = [(f or "").lstrip("#").strip() for f in (r.fieldnames or [])]
        for row in r:
            row = {(k or "").lstrip("#").strip(): v for k, v in row.items()}
            g = pick(row, "GENE_SYMBOL", "GENE")
            if g in by_gene and len(by_gene[g]) < 4:
                by_gene[g].append(row)
    return by_gene


def build_prompt(phenotype, genes, vmap, eh_flags=None):
    eh_flags = eh_flags or []
    lines = []
    lines.append("Patient HPO/phenotype terms: %s" % (phenotype or "(none provided)"))
    lines.append("")
    if eh_flags:
        lines.append("ExpansionHunter detected repeat expansion(s) in the PATHOGENIC range. "
                     "These are NOT in Exomiser's ranking below -- Exomiser cannot score "
                     "repeat expansions -- but each is an established disease mechanism and "
                     "must be treated as a leading candidate diagnosis in its own right:")
        for f in eh_flags:
            lines.append("  - %s: %s repeat genotype %s units (larger allele %d >= pathogenic "
                         "threshold %d), unit=%s at %s%s -> %s (%s)" % (
                             f["gene"], f["unit"] or "repeat", f["genotype"], f["max_allele"],
                             f["threshold"], f["unit"] or "?", f["region"] or "?",
                             (", CI " + f["ci"]) if f["ci"] else "", f["disease"], f["moi"]))
        lines.append("")
    lines.append("Exomiser ranked candidate genes (already computed from variant rarity, "
                 "in-silico pathogenicity, and HPO phenotype similarity; SNV/indel only, "
                 "repeat expansions excluded):")
    for i, g in enumerate(genes, 1):
        sym = pick(g, "GENE_SYMBOL", "GENE", default="?")
        comb = pick(g, "EXOMISER_GENE_COMBINED_SCORE", "COMBINED_SCORE", default="?")
        phen = pick(g, "EXOMISER_GENE_PHENO_SCORE", "PHENO_SCORE", default="?")
        var = pick(g, "EXOMISER_GENE_VARIANT_SCORE", "VARIANT_SCORE", default="?")
        moi = pick(g, "MOI", "MODE_OF_INHERITANCE", default="?")
        hum = pick(g, "HUMAN_PHENO_EVIDENCE", "HUMAN_PHENO_SCORE", default="")
        lines.append("  %d. %s  combined=%s pheno=%s variant=%s MOI=%s" %
                     (i, sym, comb, phen, var, moi))
        if hum:
            lines.append("       human-phenotype evidence: %s" % hum[:240])
        for v in vmap.get(sym, []):
            hgvs = pick(v, "HGVS", "FUNCTIONAL_CLASS", "VARIANT_EFFECT")
            eff = pick(v, "VARIANT_EFFECT", "FUNCTIONAL_CLASS")
            path = pick(v, "EXOMISER_VARIANT_SCORE", "VARIANT_SCORE")
            freq = pick(v, "MAX_FREQUENCY", "FREQUENCY", default="0")
            cs = pick(v, "CLINVAR_PRIMARY_INTERPRETATION", "CLINVAR", default="")
            contrib = pick(v, "CONTRIBUTING_VARIANT", default="")
            lines.append("       variant: %s effect=%s pathScore=%s maxFreq=%s clinvar=%s%s" %
                         (pick(v, "ID", "VARIANT", default="?"), eff, path, freq, cs,
                          " [contributing]" if str(contrib).lower() in ("1", "true") else ""))
    evidence = "\n".join(lines)

    # Decide whether the top candidates are effectively tied. Exomiser's combined
    # score is the authority; when the top genes sit within a small margin the LLM
    # must NOT crown a single winner (that is how a Tay-Sachs HEXA hit gets dropped
    # in favour of a fractionally-higher neighbour). Present a differential instead.
    def comb(g):
        try:
            return float(pick(g, "EXOMISER_GENE_COMBINED_SCORE", "COMBINED_SCORE", default="0") or 0)
        except ValueError:
            return 0.0
    TIE_MARGIN = 0.05
    top = comb(genes[0]) if genes else 0.0
    tied = [pick(g, "GENE_SYMBOL", "GENE", default="?") for g in genes
            if top - comb(g) <= TIE_MARGIN and comb(g) > 0]
    tie_note = (
        ("Genes within %.2f combined-score of the top are effectively TIED and must be "
         "presented as a differential, in Exomiser rank order, WITHOUT declaring one the "
         "single answer: %s." % (TIE_MARGIN, ", ".join(tied)))
        if len(tied) > 1 else
        "The top gene leads the field; you may name it as the single leading candidate."
    )

    eh_rule = (
        "- An ExpansionHunter PATHOGENIC-RANGE repeat expansion is listed above. It does "
        "NOT appear in Exomiser's gene ranking (Exomiser cannot score repeat expansions), "
        "but if its disease matches the patient's phenotype it is very likely THE diagnosis "
        "and you must lead with it, citing the gene, the repeat genotype/threshold, and the "
        "disease -- then cover the top Exomiser SNV/indel candidates as the differential.\n"
        if eh_flags else
        "- No pathogenic-range repeat expansion was reported by ExpansionHunter.\n"
    )

    instruction = textwrap.dedent("""
        You are a clinical genomics assistant. Using ONLY the evidence below, write a
        concise interpretation (5-10 sentences).

        Grounding rules (strict):
        %s- Among the Exomiser-ranked genes, rank ONLY by Exomiser's combined score. %s
        - For each candidate you discuss, cite its combined/phenotype/variant scores, the
          contributing variant(s) with their predicted effect and coordinates, and the
          mode of inheritance AS A FACT about the gene (not as evidence for or against it).
        - Do NOT introduce genes, diseases, or facts not in the evidence. Do NOT argue that
          a candidate is more or less likely based on its mode of inheritance, or on any
          outside clinical knowledge -- the scores already account for that.
        - If neither a repeat expansion nor a strong Exomiser score is present, say the
          result is inconclusive.

        --- EVIDENCE ---
        %s
        --- END EVIDENCE ---

        Interpretation:""").strip() % (eh_rule, tie_note, evidence)
    return instruction


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genes", required=True)
    ap.add_argument("--variants", default="")
    ap.add_argument("--phenotype", default=os.environ.get("GL_PHENOTYPE", ""))
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default=os.environ.get("GL_MODEL_PATH", "/model/model.gguf"))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--eh-json", dest="eh_json", default="",
                    help="ExpansionHunter JSON; pathogenic-range expansions are surfaced "
                         "as candidate diagnoses (Exomiser cannot score repeat expansions).")
    a = ap.parse_args()

    genes = read_genes(a.genes, a.top)
    if not genes:
        sys.stderr.write("genome-linter-llm: ERROR - no genes in %s\n" % a.genes)
        sys.exit(1)
    symbols = [pick(g, "GENE_SYMBOL", "GENE", default="?") for g in genes]
    vmap = variants_for(a.variants, symbols) if a.variants else {}
    eh_flags = read_eh(a.eh_json)
    if eh_flags:
        sys.stderr.write("genome-linter-llm: EH pathogenic-range expansions: %s\n" %
                         ", ".join("%s(%d)" % (f["gene"], f["max_allele"]) for f in eh_flags))
    prompt = build_prompt(a.phenotype, genes, vmap, eh_flags)

    from llama_cpp import Llama
    llm = Llama(model_path=a.model, n_ctx=8192, n_threads=os.cpu_count(), verbose=False)
    out = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2, max_tokens=600)
    text = out["choices"][0]["message"]["content"].strip()

    with open(a.output, "w") as fh:
        fh.write("# Genome-linter interpretation (Exomiser + ExpansionHunter grounded)\n\n")
        if eh_flags:
            fh.write("Pathogenic-range repeat expansions (ExpansionHunter): " + "; ".join(
                "%s %s units (>=%d) -> %s" % (f["gene"], f["genotype"], f["threshold"], f["disease"])
                for f in eh_flags) + "\n\n")
        fh.write("Top Exomiser candidates (SNV/indel): " + ", ".join(
            "%d.%s" % (i, s) for i, s in enumerate(symbols, 1)) + "\n\n")
        fh.write(text + "\n")
    sys.stderr.write("genome-linter-llm: wrote %s (%d chars)\n" % (a.output, len(text)))


if __name__ == "__main__":
    main()

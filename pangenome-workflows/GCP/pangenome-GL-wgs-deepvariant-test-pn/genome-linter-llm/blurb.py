#!/usr/bin/env python3
"""Grounded genome-linter: turn Exomiser's ranked output into a readable clinical
interpretation using a LOCAL small LLM (no network / no OpenRouter).

Design: the LLM does NOT rank or recall genes. Exomiser already produced a grounded
ranking from variant rarity + pathogenicity + HPO semantic similarity. This script
feeds the LLM ONLY that evidence (top genes, their scores, and the contributing
variants) and asks it to summarise — so it cannot hallucinate a gene that the
variant evidence does not support (the old failure mode that buried HEXA).
"""
import argparse, csv, os, sys, textwrap


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


def build_prompt(phenotype, genes, vmap):
    lines = []
    lines.append("Patient HPO/phenotype terms: %s" % (phenotype or "(none provided)"))
    lines.append("")
    lines.append("Exomiser ranked candidate genes (already computed from variant rarity, "
                 "in-silico pathogenicity, and HPO phenotype similarity):")
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

    instruction = textwrap.dedent("""
        You are a clinical genomics assistant. Using ONLY the Exomiser evidence below,
        write a concise interpretation (5-10 sentences).

        Grounding rules (strict):
        - Rank ONLY by Exomiser's combined score. %s
        - For each candidate you discuss, cite its combined/phenotype/variant scores, the
          contributing variant(s) with their predicted effect and coordinates, and the
          mode of inheritance AS A FACT about the gene (not as evidence for or against it).
        - Do NOT introduce genes, diseases, or facts not in the evidence. Do NOT argue that
          a candidate is more or less likely based on its mode of inheritance, or on any
          outside clinical knowledge -- the scores already account for that.
        - If the leading score is weak, say the result is inconclusive.

        --- EVIDENCE ---
        %s
        --- END EVIDENCE ---

        Interpretation:""").strip() % (tie_note, evidence)
    return instruction


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genes", required=True)
    ap.add_argument("--variants", default="")
    ap.add_argument("--phenotype", default=os.environ.get("GL_PHENOTYPE", ""))
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default=os.environ.get("GL_MODEL_PATH", "/model/model.gguf"))
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    genes = read_genes(a.genes, a.top)
    if not genes:
        sys.stderr.write("genome-linter-llm: ERROR - no genes in %s\n" % a.genes)
        sys.exit(1)
    symbols = [pick(g, "GENE_SYMBOL", "GENE", default="?") for g in genes]
    vmap = variants_for(a.variants, symbols) if a.variants else {}
    prompt = build_prompt(a.phenotype, genes, vmap)

    from llama_cpp import Llama
    llm = Llama(model_path=a.model, n_ctx=8192, n_threads=os.cpu_count(), verbose=False)
    out = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2, max_tokens=600)
    text = out["choices"][0]["message"]["content"].strip()

    with open(a.output, "w") as fh:
        fh.write("# Genome-linter interpretation (Exomiser-grounded)\n\n")
        fh.write("Top Exomiser candidates: " + ", ".join(
            "%d.%s" % (i, s) for i, s in enumerate(symbols, 1)) + "\n\n")
        fh.write(text + "\n")
    sys.stderr.write("genome-linter-llm: wrote %s (%d chars)\n" % (a.output, len(text)))


if __name__ == "__main__":
    main()

# Changelog — pangenome DeepVariant test workflow

All notable changes to the annotation/interpretation tail of this workflow
(`main-vg.cwl`: VEP → slivar → genome-linter) are documented here.

## [Unreleased] — Phenotype-driven prioritisation + grounded interpretation

This release replaces the phenotype-label-only LLM "genome-linter" with an
evidence-grounded two-step tail (**Exomiser** → **local-LLM narrative**) and
strengthens the slivar rare-variant gate. Validated on the cborg Arvados cluster
against a Tay-Sachs DeepVariant call set.

### Added

- **`exomiser.cwl`** — phenotype-driven gene/variant prioritisation with
  [Exomiser](https://github.com/exomiser/Exomiser) 15.0.0 (open source). Consumes
  the normalized VCF + an HPO term list and ranks candidate genes from variant
  rarity, in-silico pathogenicity (REVEL/MVP/AlphaMissense/SpliceAI) and HPO
  semantic similarity. Outputs `genes.tsv`, `variants.tsv`, `json` (JSON-Lines),
  and an HTML report.
  - **`exomiser-wrapper/`** — self-contained image (`nelly-exomiser`): an
    `eclipse-temurin:21-jre` base + the exomiser-cli distribution + `run-exomiser.sh`.
    Built our own because the official `exomiser/exomiser-cli` image is distroless
    (no shell, fixed jib entrypoint) and cannot run a setup script. `run-exomiser.sh`
    auto-detects a `data/` prefix in the mounted Keep bundle, derives the proband id
    from the VCF sample column (Exomiser aborts on a mismatch), and writes the
    `application.properties`/`phenopacket.yml`/`analysis.yml` at run time.
- **`genome-linter-llm.cwl`** — a LOCAL small LLM (Qwen2.5-3B-Instruct Q4_K_M,
  baked into the image; no network at run time) writes a clinical interpretation of
  Exomiser's ranked output. It only *summarises supplied evidence* — it does not
  rank or recall genes — so it cannot bury the true causative gene the way the old
  phenotype-label-only ranker did.
  - **`genome-linter-llm/`** — image (`nelly-genome-linter-llm`) + `blurb.py`.
    `llama-cpp-python` is built from source against the image's glibc (the prebuilt
    CPU wheels are musl-linked and will not load on Debian); `CMAKE_ARGS=-DGGML_NATIVE=OFF`
    keeps the binary portable across the workstation and the cluster's CPUs.
- **`test-exomiser-gl.cwl`** (+ `.inputs.json`) — standalone two-step validation
  workflow (exomiser → genome-linter-llm) on an already-produced normalized VCF, so
  the deployment can be tested without rerunning the hours-long pangenome pipeline.
- **`test-gl-only.inputs.json`** — inputs to exercise just the LLM step against
  pre-computed Exomiser TSVs (fast iteration on the narrative).

### Changed

- **`main-vg.cwl`** — the OpenRouter `genomelinter` step is replaced by
  `exomiser` (consumes the bcftools-normalized VCF) → `genomelinter`
  (consumes Exomiser's gene/variant tables + the phenotype). New inputs:
  `exomiser_data` (Keep Directory), `exomiser_assembly` (default `hg38`),
  `exomiser_data_version` (default `2512`), `hpo_terms`, `sample_sex`
  (default `UNKNOWN`), `exomiser_top_genes` (default `10`). New outputs:
  `output_exomiser_genes`, `output_exomiser_variants`, `output_exomiser_html`.
- **`slivar.cwl` / `main-vg.cwl`** — strengthened the rare-variant gate:
  - `slivar_info` tightened to
    `INFO.gnomad_popmax_af < 0.001 && INFO.gnomad_nhomalt <= 3 && variant.FILTER == 'PASS'`.
  - added a per-sample quality/zygosity gate `slivar_sample_expr`
    (default `high_quality:sample.GQ >= 20 && sample.DP >= 10 && (sample.het || sample.hom_alt)`).
- **`genome-linter-llm/blurb.py`** — when the top candidate genes fall within a
  small combined-score margin (0.05) they are presented as a **differential in
  Exomiser rank order** rather than crowning a single winner, and the prompt
  forbids likelihood arguments from mode-of-inheritance or any outside knowledge
  (the scores already account for those). Prevents a fractionally-higher neighbour
  from displacing a genuine hit (e.g. HEXA in a Tay-Sachs sample).

### Fixed

- **`phenofrommetadata.cwl`** — stopped wrapping the phenotype string in literal
  double-quotes (`outputEval` now strips trailing newlines instead). Combined with
  the genome-linter re-wrapping, the old behaviour produced `""Chorea;Huntington
  disease""`; the embedded `;` split the downstream shell command and silently
  dropped the VCF.
- **`genome-linter.cwl`** (legacy OpenRouter tool, retained) — phenotype is now
  passed via an env var (`GL_PHENOTYPE`) instead of being interpolated into the
  command line, and the step fails loud (`grep -qvE '^#' input.vcf || exit 1`)
  instead of going green on an empty VCF.
- **`exomiser.cwl`** — the JSON output glob now matches Exomiser 15's actual
  filename `results/exomiser.jsonl` (JSON-Lines), not `exomiser.json`. The wrong
  name failed the whole step (`permanentFail`) and discarded the valid
  `genes.tsv`/`variants.tsv`/`html`.

### Deployment notes (Arvados / cborg)

- Wrapper images carry **no `ENTRYPOINT`** (CMD only): the Arvados runtime prepends
  the image ENTRYPOINT to the CWL command, which doubled `baseCommand` and shifted
  the positional arguments.
- Both `$(...)` **and** `${...}` are interpreted as CWL expressions regardless of
  `InlineJavascriptRequirement`, and `cwltool --validate` does not catch it — so all
  shell logic lives inside the wrapper images (`run-exomiser.sh`, `blurb.py`), not
  inline in the CWL.
- Exomiser data bundle (`2512_hg38` + `2512_phenotype`, ~55 GB unpacked) is a Keep
  collection passed as the `exomiser_data` Directory input.

### Validation

Standalone test on the cborg cluster, Tay-Sachs DeepVariant VCF, with a deliberately
**disguised** phenotype (`HP:0000726` "Dementia", not an obvious Tay-Sachs term):

- Exomiser ranked **HEXA #2 of 823 genes** (combined 0.9893, variant score 1.0000),
  linked to GM2-gangliosidosis (OMIM:272800); the planted Huntington *HTT* locus
  ranked lower (#6), as expected for this sample.
- The full `exomiser → genome-linter-llm` pipeline completed green (exit 0); the
  local LLM produced a grounded narrative citing the true variant
  `15-72346234-C-G`, with no hallucinated genes.

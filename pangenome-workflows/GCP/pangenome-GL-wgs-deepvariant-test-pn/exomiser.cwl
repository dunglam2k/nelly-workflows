cwlVersion: v1.1
class: CommandLineTool
# Phenotype-driven gene/variant prioritisation with Exomiser (open source),
# replacing the phenotype-label-only LLM ranker. The setup logic lives in
# /run-exomiser.sh INSIDE the wrapper image (nelly-exomiser:v3 = JRE + exomiser
# dist + script), so there is NO inline shell here and therefore no CWL string
# interpolation of bash. Values are passed as clean positional arguments.
baseCommand: [bash, /run-exomiser.sh]
requirements:
  ResourceRequirement:
    ramMin: 32768
    coresMin: 4
  DockerRequirement:
    dockerPull: 'nelly-exomiser:v3'
arguments:
  - position: 1
    valueFrom: $(inputs.exomiser_data.path)
  - position: 2
    valueFrom: $(inputs.exomiser_vcf.path)
  - position: 3
    valueFrom: $(inputs.exomiser_assembly)
  - position: 4
    valueFrom: $(inputs.exomiser_data_version)
  - position: 5
    valueFrom: $(inputs.hpo_terms)
  - position: 6
    valueFrom: $(inputs.sample_sex)
inputs:
  exomiser_vcf:
    # Exomiser streams the (b)gzipped VCF directly; no .tbi index required.
    type: File
  exomiser_data:
    type: Directory
  exomiser_assembly:
    type: string
    default: "hg38"
  exomiser_data_version:
    type: string
    default: "2512"
  hpo_terms:
    type: string
  sample_sex:
    type: string
    default: "UNKNOWN"
outputs:
  exomiser_genes_tsv:
    type: File
    outputBinding:
      glob: "results/exomiser.genes.tsv"
  exomiser_variants_tsv:
    type: File
    outputBinding:
      glob: "results/exomiser.variants.tsv"
  exomiser_json:
    # Exomiser 15 writes the JSON output as JSON-Lines: exomiser.jsonl (one JSON
    # object per line), NOT exomiser.json. Globbing the wrong name fails the whole
    # step (permanentFail) even though genes/variants/html were produced fine.
    type: File
    outputBinding:
      glob: "results/exomiser.jsonl"
  exomiser_html:
    type: File
    outputBinding:
      glob: "results/exomiser.html"

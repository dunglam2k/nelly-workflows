cwlVersion: v1.1
class: CommandLineTool
# Grounded genome-linter: a LOCAL small LLM (Qwen2.5-3B, baked into the image)
# writes a clinical interpretation of Exomiser's ranked output. It only summarises
# the supplied evidence -- it does not rank or recall genes -- so it cannot bury
# the true causative gene the way the old phenotype-label-only ranker did.
#
# Direct command (no inline shell): blurb.py reads the phenotype from $GL_PHENOTYPE.
baseCommand: [python, /app/blurb.py]
requirements:
  ResourceRequirement:
    ramMin: 12288
    coresMin: 8
  EnvVarRequirement:
    envDef:
      GL_PHENOTYPE: $(inputs.phenotype)
  DockerRequirement:
    dockerPull: 'nelly-genome-linter-llm:v3'
arguments:
  - prefix: --genes
    valueFrom: $(inputs.exomiser_genes_tsv.path)
  - prefix: --variants
    valueFrom: $(inputs.exomiser_variants_tsv.path)
  - prefix: --top
    valueFrom: $(inputs.top_genes)
  - prefix: --output
    valueFrom: $(inputs.output_name)
inputs:
  exomiser_genes_tsv:
    type: File
  exomiser_variants_tsv:
    type: File
  phenotype:
    type: string
    default: ""
  top_genes:
    type: int
    default: 10
  output_name:
    type: string
    default: "genomelinter-output.txt"
outputs:
  genomelinter_output:
    type: File
    outputBinding:
      glob: $(inputs.output_name)

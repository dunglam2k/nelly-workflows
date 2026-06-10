cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  DockerRequirement:
    dockerPull: "brentp/slivar:v0.3.0"
  ResourceRequirement:
    ramMin: $(8 * 1024)
baseCommand: slivar
arguments: [expr,
 -g, $(inputs.slivar_gnomad),
  --vcf, $(inputs.slivar_input),
  --info, $(inputs.slivar_info),
  --sample-expr, $(inputs.slivar_sample_expr), --pass-only,
  -o, "slivar-output.vcf.gz"
]

inputs:
  slivar_gnomad:
    type: File
  slivar_input:
    type: File
    secondaryFiles:
      - .tbi
  slivar_info:
    type: string
  slivar_sample_expr:
    type: string
    # Per-sample genotype-quality gate (e.g.
    # "high_quality:sample.GQ >= 20 && sample.DP >= 10 && (sample.het || sample.hom_alt)").
    # With --pass-only a variant is kept iff it is rare (--info) AND at least one
    # sample passes this expression, removing low-quality / hom-ref noise.
    default: "high_quality:sample.GQ >= 20 && sample.DP >= 10 && (sample.het || sample.hom_alt)"

outputs:
  slivar_output:
    type: File
    outputBinding:
      glob: "slivar-output.vcf.gz"


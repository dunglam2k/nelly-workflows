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
  --info, $(inputs.slivar_info), --pass-only,
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

outputs:
  slivar_output:
    type: File
    outputBinding:
      glob: "slivar-output.vcf.gz"


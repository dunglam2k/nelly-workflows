cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  DockerRequirement:
    dockerPull: "staphb/bcftools:1.19"
  ResourceRequirement:
    coresMin: 4
    ramMin: $(8 * 1024)
baseCommand: bash
arguments:
  - -c
  - |
    set -euo pipefail
    bcftools norm --threads $(runtime.cores) -f "$(inputs.ref.path)" -m -any -Oz -o "$(inputs.output_name)" "$(inputs.input_vcf.path)"
    bcftools index --threads $(runtime.cores) -t "$(inputs.output_name)"

inputs:
  input_vcf:
    type: File
    secondaryFiles:
      - .tbi
  ref:
    type: File
    secondaryFiles:
      - .fai
  output_name:
    type: string
    default: normalized.vcf.gz

outputs:
  normalized_vcf:
    type: File
    secondaryFiles:
      - .tbi
    outputBinding:
      glob: $(inputs.output_name)

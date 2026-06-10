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
    # DeepVariant names the sample from the read-group SM ("sample"); ExpansionHunter
    # names it from the input filename ("aligned.sorted.markdup"). bcftools concat
    # requires identical sample names, so reheader vcf_b to match vcf_a first.
    bcftools query -l "$(inputs.vcf_a.path)" | head -1 > sample_name.txt
    bcftools reheader -s sample_name.txt -o vcf_b.renamed.vcf.gz "$(inputs.vcf_b.path)"
    bcftools index -t vcf_b.renamed.vcf.gz
    bcftools concat --threads $(runtime.cores) --allow-overlaps --rm-dups all -Oz -o "$(inputs.output_name)" "$(inputs.vcf_a.path)" vcf_b.renamed.vcf.gz
    bcftools sort -Oz -o "$(inputs.output_name).sorted" "$(inputs.output_name)"
    mv "$(inputs.output_name).sorted" "$(inputs.output_name)"
    bcftools index --threads $(runtime.cores) -t "$(inputs.output_name)"

inputs:
  vcf_a:
    type: File
    secondaryFiles:
      - .tbi
  vcf_b:
    type: File
    secondaryFiles:
      - .tbi
  output_name:
    type: string
    default: combined.vcf.gz

outputs:
  combined_vcf:
    type: File
    secondaryFiles:
      - .tbi
    outputBinding:
      glob: $(inputs.output_name)

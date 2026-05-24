cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  DockerRequirement:
    dockerPull: "quay.io/biocontainers/expansionhunter:5.0.0--h27087fc_1"
  ResourceRequirement:
    coresMin: 8
    ramMin: $(16 * 1024)
baseCommand: bash
arguments:
  - -c
  - |
    set -euo pipefail
    # ExpansionHunter v5 takes CRAM/BAM with index, FASTA with .fai, JSON catalog, and an output prefix.
    # Sex defaults to "female" if not provided; for known clinical loci this is the safer default
    # because HTT (autosomal) is genotyped identically either way and X-linked loci (FMR1, etc.)
    # will be called as a single allele when --sex male is supplied.
    ExpansionHunter \
      --reads "$(inputs.aligned_reads.path)" \
      --reference "$(inputs.ref.path)" \
      --variant-catalog "$(inputs.variant_catalog.path)" \
      --sex "$(inputs.sex)" \
      --output-prefix "$(inputs.output_prefix)" \
      --threads $(runtime.cores)
    # ExpansionHunter writes .vcf (uncompressed). bgzip + tabix-index so downstream concat works.
    bgzip -f "$(inputs.output_prefix).vcf"
    tabix -p vcf "$(inputs.output_prefix).vcf.gz"

inputs:
  aligned_reads:
    type: File
    secondaryFiles:
      - .crai
  ref:
    type: File
    secondaryFiles:
      - .fai
  variant_catalog:
    type: File
  sex:
    type:
      type: enum
      symbols: [male, female]
    default: female
  output_prefix:
    type: string
    default: eh_repeats

outputs:
  vcf:
    type: File
    secondaryFiles:
      - .tbi
    outputBinding:
      glob: $(inputs.output_prefix).vcf.gz
  json:
    type: File
    outputBinding:
      glob: $(inputs.output_prefix).json
  realigned_bam:
    type: File?
    outputBinding:
      glob: $(inputs.output_prefix)_realigned.bam

cwlVersion: v1.1
class: Workflow
requirements:
  InlineJavascriptRequirement: {}
  ResourceRequirement:
    ramMin: $(1 * 1024)
    coresMin: 1
  MultipleInputFeatureRequirement: {}

inputs:
  ref_prefix:
    type: string
    default: GRCh38
  sample_name:
    type: string
    default: sample
  sex:
    type:
      type: enum
      symbols: [male, female]
    default: female
  graph:
    type: File
  ref:
    type: File
    secondaryFiles:
      - .fai
  reads1: File
  reads2: File
  dist: File
  min: File
  aligned_bam_output:
    type: string
    default: aligned.bam
  dv_model_type:
    type: string
    default: WGS
  dv_output_vcf:
    type: string
    default: variants.dv.vcf.gz
  dv_output_gvcf:
    type: string
    default: variants.dv.gvcf.gz
  eh_variant_catalog: File
  eh_output_prefix:
    type: string
    default: eh_repeats
  combined_vcf_name:
    type: string
    default: combined.vcf.gz
  normalized_vcf_name:
    type: string
    default: normalized.vcf.gz
  slivar_gnomad: File
  slivar_info:
    type: string
    default: "INFO.gnomad_popmax_af < 0.01 && variant.FILTER == 'PASS'"
  vep_assembly:
    type: string
    default: GRCh38
  vep_output_file:
    type: string
    default: vep-output.vcf.gz
  pavs_custom_file:
    type: File
    secondaryFiles:
      - .tbi
  pavs_custom_args: string
  go_custom_file:
    type: File
    secondaryFiles:
      - .tbi
  go_custom_args: string
  hpo_custom_file:
    type: File
    secondaryFiles:
      - .tbi
  hpo_custom_args: string
  ppi_custom_file:
    type: File
    secondaryFiles:
      - .tbi
  ppi_custom_args: string
  vep_dir: Directory
  vep_fasta_file: File
  metadata: File
  genomelinter_output_name:
    type: string
    default: "genomelinter-output.txt"
  genomelinter_model:
    type: string
    default: "openai/gpt-oss-20b:free"
  openrouter_api_key:
    type: string
    default: ""

outputs:
  output_aligned_cram:
    type: File
    outputSource: samtools-markdup-index/aligned_reads_indexed
  output_dv_vcf:
    type: File
    outputSource: deepvariant/vcf
  output_dv_gvcf:
    type: File
    outputSource: deepvariant/gvcf
  output_eh_vcf:
    type: File
    outputSource: expansionhunter/vcf
  output_eh_json:
    type: File
    outputSource: expansionhunter/json
  output_combined_vcf:
    type: File
    outputSource: bcftools-norm/normalized_vcf
  output_slivar:
    type: File
    outputSource: slivar/slivar_output
  output_after_vep:
    type: File
    outputSource: vep/vep_output
  output_after_genomelinter:
    type: File
    outputSource: genomelinter/genomelinter_output

steps:
  vg-paths:
    in:
      graph: graph
      ref_prefix: ref_prefix
    out: [path_list]
    run: vg-paths.cwl

  vg-giraffe-bam:
    in:
      graph: graph
      reads1: reads1
      reads2: reads2
      ref_paths: vg-paths/path_list
      dist: dist
      min: min
      sample_name: sample_name
      bam_output: aligned_bam_output
    out: [aligned_reads]
    run: vg-giraffe-bam.cwl

  samtools-sort:
    in:
      aligned_reads: vg-giraffe-bam/aligned_reads
      ref: ref
      ref_prefix: ref_prefix
    out: [aligned_reads_sorted]
    run: samtools-sort.cwl

  samtools-index-sorted:
    in:
      aligned_reads: samtools-sort/aligned_reads_sorted
    out: [aligned_reads_indexed]
    run: samtools-index.cwl

  samtools-markdup:
    in:
      aligned_reads: samtools-index-sorted/aligned_reads_indexed
      ref: ref
    out: [marked_reads]
    run: samtools-markdup.cwl

  samtools-markdup-index:
    in:
      aligned_reads: samtools-markdup/marked_reads
    out: [aligned_reads_indexed]
    run: samtools-index.cwl

  deepvariant:
    in:
      model_type: dv_model_type
      ref: ref
      aligned_reads: samtools-markdup-index/aligned_reads_indexed
      output_vcf: dv_output_vcf
      output_gvcf: dv_output_gvcf
    out: [vcf, gvcf]
    run: deepvariant.cwl

  expansionhunter:
    in:
      aligned_reads: samtools-markdup-index/aligned_reads_indexed
      ref: ref
      variant_catalog: eh_variant_catalog
      sex: sex
      output_prefix: eh_output_prefix
    out: [vcf, json]
    run: expansionhunter.cwl

  bcftools-concat:
    in:
      vcf_a: deepvariant/vcf
      vcf_b: expansionhunter/vcf
      output_name: combined_vcf_name
    out: [combined_vcf]
    run: bcftools-concat.cwl

  bcftools-norm:
    in:
      input_vcf: bcftools-concat/combined_vcf
      ref: ref
      output_name: normalized_vcf_name
    out: [normalized_vcf]
    run: bcftools-norm.cwl

  slivar:
    in:
      slivar_gnomad: slivar_gnomad
      slivar_input: bcftools-norm/normalized_vcf
      slivar_info: slivar_info
    out: [slivar_output]
    run: slivar.cwl

  vep:
    in:
      vep_input: [slivar/slivar_output]
      vep_assembly: vep_assembly
      vep_output_file: vep_output_file
      pavs_custom_file: pavs_custom_file
      pavs_custom_args: pavs_custom_args
      go_custom_file: go_custom_file
      go_custom_args: go_custom_args
      hpo_custom_file: hpo_custom_file
      hpo_custom_args: hpo_custom_args
      ppi_custom_file: ppi_custom_file
      ppi_custom_args: ppi_custom_args
      vep_dir: vep_dir
      vep_fasta_file: vep_fasta_file
    out: [vep_console_out, vep_output]
    run: vep.cwl

  phenofrommetadata:
    in:
      metadata: metadata
    out: [pheno_output]
    run: phenofrommetadata.cwl

  genomelinter:
    in:
      openrouter_api_key: openrouter_api_key
      genomelinter_output_name: genomelinter_output_name
      genomelinter_model: genomelinter_model
      genomelinter_phenotypes: [phenofrommetadata/pheno_output]
      genomelinter_input: [vep/vep_output]
    out: [genomelinter_output]
    run: genome-linter.cwl

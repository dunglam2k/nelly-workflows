cwlVersion: v1.1
class: Workflow
requirements:
  InlineJavascriptRequirement: {}
#  ShellCommandRequirement: {}
  ResourceRequirement:
    ramMin: $(1 * 1024)
    coresMin: 1
  MultipleInputFeatureRequirement: {}
  
inputs:
  ref_prefix: string
  graph:
    type: File
  reads1: File
  reads2: File
  dist: File
  min: File
  snarl: File
  output_gam: string?
  output_vcf: string?
  slivar_gnomad: File
  # slivar_ped: File
  slivar_info: string
  vep_assembly: string
  vep_output_file: string
  pavs_custom_file: File
  pavs_custom_args: string
  go_custom_file: File
  go_custom_args: string
  hpo_custom_file: File
  hpo_custom_args: string
  ppi_custom_file: File
  ppi_custom_args: string
  vep_dir: Directory
  vep_fasta_file: File
  metadata: File
  genomelinter_output_name: string?
  genomelinter_model: string?
  
outputs:
  output_vcf:
    type: File
    outputSource: vg-call/vcf 
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
  vg-giraffe-and-pack:
    in:
      graph: graph
      reads1: reads1
      reads2: reads2
      ref_paths: vg-paths/path_list
      dist: dist
      min: min
      gam_output: output_gam
    out: [pack]
    run: vg-giraffe-and-pack.cwl
  vg-call:
    in:
      graph: graph
      snarl: snarl
      pack: vg-giraffe-and-pack/pack
      output: output_vcf
    out: [vcf]
    run: vg-call.cwl
  slivar:
    in:
      slivar_gnomad: slivar_gnomad
      slivar_input: vg-call/vcf
    #  slivar_ped: slivar_ped
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
      genomelinter_output_name: genomelinter_output_name
      genomelinter_model: genomelinter_model
      genomelinter_phenotypes: [phenofrommetadata/pheno_output]
      genomelinter_input: [vep/vep_output]
    out: [genomelinter_output]
    run: genome-linter.cwl



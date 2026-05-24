cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  DockerRequirement:
    dockerPull: "google/deepvariant:1.6.0"
  ResourceRequirement:
    coresMin: 8
    ramMin: $(90 * 1024)
baseCommand: /opt/deepvariant/bin/run_deepvariant

inputs:
  model_type:
    type: string
    default: WGS
    inputBinding:
      prefix: --model_type
  ref:
    type: File
    secondaryFiles:
      - .fai
    inputBinding:
      prefix: --ref
  aligned_reads:
    type: File
    secondaryFiles:
      - .crai
    inputBinding:
      prefix: --reads
  output_vcf:
    type: string
    default: variants.vcf.gz
    inputBinding:
      prefix: --output_vcf
  output_gvcf:
    type: string
    default: variants.gvcf.gz
    inputBinding:
      prefix: --output_gvcf
  num_shards:
    type: int
    default: 64
    inputBinding:
      prefix: --num_shards
      valueFrom: $(runtime.cores)
  intermediate_results_dir:
    type: string
    default: dv_intermediate
    inputBinding:
      prefix: --intermediate_results_dir
  regions:
    type: File?
    inputBinding:
      prefix: --regions

outputs:
  vcf:
    type: File
    secondaryFiles:
      - .tbi
    outputBinding:
      glob: $(inputs.output_vcf)
  gvcf:
    type: File
    secondaryFiles:
      - .tbi
    outputBinding:
      glob: $(inputs.output_gvcf)

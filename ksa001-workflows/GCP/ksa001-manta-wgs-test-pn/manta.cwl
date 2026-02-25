cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  InitialWorkDirRequirement:
    listing: [ $(inputs.aligned_reads) ]

  DockerRequirement:
    dockerPull: "quay.io/biocontainers/manta:1.6.0--h9ee0642_3"
  ResourceRequirement:
    coresMin: 2
    ramMin: $(4 * 1024)
baseCommand: configManta.py
arguments: [--bam, $(inputs.aligned_reads), '--referenceFasta',
           $(inputs.ref), '--runDir', $(inputs.run_dir),
           {shellQuote: false, valueFrom: '&&'},
            $(inputs.run_dir)/runWorkflow.py] 
inputs:
  aligned_reads:
    type: File
    secondaryFiles:
      - .crai ?
      - .bai ?
  ref:
    type: File
    secondaryFiles:
      - .fai
  run_dir:
    type: string
    default: '.'
      
outputs:
  diploidsv_vcf:
    type: File
    secondaryFiles:
      - .tbii
    outputBinding:
      glob: $(inputs.run_dir + '/results/variants/diploidSV.vcf.gz')

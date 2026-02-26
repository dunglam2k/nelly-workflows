cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  DockerRequirement:
    dockerPull: "quay.io/biocontainers/vg:1.54.0--h9ee0642_0"
  ResourceRequirement:
    coresMin: 10
    ramMin: $(64 * 1024)
baseCommand: vg
arguments: [call, $(inputs.graph), -k, $(inputs.pack), -r, $(inputs.snarl), -s, $(inputs.sample),
           -t, $(runtime.cores), -S, "GRCh38", -z, 
           {shellQuote: false, valueFrom: '|'}, 
           sed, -e, 's/GRCh38#0#//g',
           {shellQuote: false, valueFrom: '|'},
           tee, $(inputs.output)
           ]

inputs:
  graph:
    type: File
  snarl:
    type: File 
  pack:
    type: File
  sample:
    type: string
    default: sample
  output:
    type: string
    default: genotypes.vcf

#outputs:
  #vcf:
    #type: stdout

#stdout: $(inputs.output)

outputs:
  vcf:
    type: File
    outputBinding:
      glob: $(inputs.output)
    

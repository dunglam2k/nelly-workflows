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
arguments: [pack, -Q, "5", -t, $(runtime.cores)]

inputs:
  graph:
    type: File
    inputBinding:
      prefix: -x
  gam:
    type: File
    inputBinding:
      prefix: -g
  pack-output:
    type: string
    default: output.pack
    inputBinding:
      prefix: -o
outputs:
  pack:
    type: File
    outputBinding:
      glob: '*.pack'

cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  DockerRequirement:
    dockerPull: "quay.io/biocontainers/vg:1.54.0--h9ee0642_0"
  ResourceRequirement:
    coresMin: 5
    ramMin: $(64 * 1024)

baseCommand: [vg]
arguments: [giraffe, -p, -t, $(runtime.cores), -Z, $(inputs.graph), --ref-paths, $(inputs.ref_paths), -f, $(inputs.reads1), 
            -f, $(inputs.reads2), -d, $(inputs.dist), -m, $(inputs.min), --rescue-attempts, "2", --rescue-subgraph-size, "2", 
            --rescue-seed-limit, "32", --max-dp-cells, "4000000",
            {shellQuote: false, valueFrom: '|'} , 
            vg, pack, -Q, "5", -t, $(runtime.cores), -x, $(inputs.graph), -g, -, -o, $(inputs.pack_output)
           ]

#arguments: 
#        [vg giraffe -p, -t $(runtime.cores) -Z $(inputs.graph) --ref-paths $(inputs.ref_paths) -f $(inputs.reads1)  
#        -f $(inputs.reads2) -d $(inputs.dist) -m $(inputs.min) > $(inputs.gam_output) | 
#        vg pack -Q "5" -t $(runtime.cores) -x $(inputs.graph) -g $(inputs.gam_output) -o $(inputs.pack_output)]
           

inputs:
  graph:
    type: File
  ref_paths:
    type: File
  reads1:
    type: File
  reads2:
    type: File?
  dist:
    type: File
  min:
    type: File
  gam_output:
    type: string
    default: output.gam
  pack_output:
    type: string
    default: output.pack
outputs:
  pack:
    type: File
    outputBinding:
      glob: '*.pack'
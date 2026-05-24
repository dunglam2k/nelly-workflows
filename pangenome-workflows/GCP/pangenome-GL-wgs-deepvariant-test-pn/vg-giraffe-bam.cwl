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

baseCommand: [vg]
arguments:
  - giraffe
  - -p
  - -t
  - $(runtime.cores)
  - -Z
  - $(inputs.graph)
  - --ref-paths
  - $(inputs.ref_paths)
  - -f
  - $(inputs.reads1)
  - -f
  - $(inputs.reads2)
  - -d
  - $(inputs.dist)
  - -m
  - $(inputs.min)
  - --output-format
  - BAM
  - --sample
  - $(inputs.sample_name)
  - --read-group
  - "ID:$(inputs.sample_name)\tSM:$(inputs.sample_name)\tLB:$(inputs.sample_name)\tPL:ILLUMINA"
  # Mate rescue on complex graphs (large pangenomes like ksa_hg38) caused
  # OOM / never-finishing runs with the default dozeu algorithm. The vg team's
  # Giraffe best-practices page recommends disabling rescue entirely for
  # complex graphs: https://github.com/vgteam/vg/wiki/Giraffe-best-practices
  - --rescue-algorithm
  - none
  - --max-dp-cells
  - "4000000"

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
  sample_name:
    type: string
    default: sample
  bam_output:
    type: string
    default: aligned.bam

outputs:
  aligned_reads:
    type: stdout

stdout: $(inputs.bam_output)

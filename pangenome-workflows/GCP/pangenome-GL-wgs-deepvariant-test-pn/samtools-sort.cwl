cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  InitialWorkDirRequirement:
    listing: [ $(inputs.aligned_reads) ]
  DockerRequirement:
    dockerPull: "coolmaksat/minimap2-samtools"
  ResourceRequirement:
    coresMin: 8
    ramMin: $(16 * 1024)
baseCommand: bash
arguments:
  - -c
  - |
    set -euo pipefail
    samtools view -h "$(inputs.aligned_reads.path)" \
      | sed -e 's/$(inputs.ref_prefix)#0#//g' \
      | samtools sort -@ $(runtime.cores) \
                      -O CRAM \
                      --reference "$(inputs.ref.path)" \
                      -T "$(runtime.tmpdir)/sort." \
                      -o "$(inputs.aligned_reads.nameroot).sorted.cram" -
inputs:
  aligned_reads:
    type: File
  ref:
    type: File
    secondaryFiles:
      - .fai
  ref_prefix:
    type: string
    default: GRCh38

outputs:
  aligned_reads_sorted:
    type: File
    outputBinding:
      glob: $(inputs.aligned_reads.nameroot).sorted.cram

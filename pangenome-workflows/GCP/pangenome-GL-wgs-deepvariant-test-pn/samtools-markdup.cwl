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
    # markdup needs name-sorted-then-fixmate-ed input. Pipe through collate→fixmate→sort→markdup.
    # NB: trailing-pipe continuation only (NO backslash). CWL interpolation strips
    # a "\" before a newline, which would orphan the leading "|" on the next line
    # and break bash with "syntax error near unexpected token '|'".
    samtools collate -@ $(runtime.cores) -O -u --reference "$(inputs.ref.path)" "$(inputs.aligned_reads.path)" "$(runtime.tmpdir)/collate" |
      samtools fixmate -@ $(runtime.cores) -m -u - - |
      samtools sort -@ $(runtime.cores) -u --reference "$(inputs.ref.path)" -T "$(runtime.tmpdir)/sort." -o - - |
      samtools markdup -@ $(runtime.cores) --reference "$(inputs.ref.path)" -O CRAM -T "$(runtime.tmpdir)/markdup." - "$(inputs.aligned_reads.nameroot).markdup.cram"
inputs:
  aligned_reads:
    type: File
    secondaryFiles:
      - .crai
  ref:
    type: File
    secondaryFiles:
      - .fai

outputs:
  marked_reads:
    type: File
    outputBinding:
      glob: $(inputs.aligned_reads.nameroot).markdup.cram

cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing: [ $(inputs.aligned_reads) ]
  DockerRequirement:
    dockerPull: "coolmaksat/minimap2-samtools"
  ResourceRequirement:
    coresMin: 8
    ramMin: $(16 * 1024)
baseCommand: bash
# NOTE: the pipeline below uses a trailing-pipe ("|" at end of line) for line
# continuation, NOT backslash continuation. CWL string interpolation treats "\"
# as an escape character, so a "\" before a newline is silently stripped during
# $(...) expansion, which collapses the pipeline onto one line and makes bash
# fail with "syntax error near unexpected token '|'". A trailing "|" continues
# the command in bash without any backslash, so it survives interpolation.
arguments:
  - -c
  - |
    set -euo pipefail
    # NB: the @RG separators are written as "\\t" (double backslash). CWL string
    # interpolation strips a single backslash from EVERY "\x" (so "\t" -> "t"),
    # which would feed samtools a tab-less "@RGtID:..." and break it. "\\t"
    # survives interpolation as a literal "\t", which samtools addreplacerg then
    # converts to a real tab.
    samtools view -h "$(inputs.aligned_reads.path)" |
      sed -e 's/$(inputs.ref_prefix)#0#//g' |
      samtools addreplacerg -w -r "@RG\\tID:$(inputs.sample_name)\\tSM:$(inputs.sample_name)\\tLB:$(inputs.sample_name)\\tPL:ILLUMINA" -O sam - |
      samtools sort -@ $(runtime.cores) -O CRAM --reference "$(inputs.ref.path)" -T "$(runtime.tmpdir)/sort." -o "$(inputs.aligned_reads.nameroot).sorted.cram" -
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
  # Full @RG metadata is set HERE (not in vg-giraffe-bam) because vg giraffe's
  # --read-group accepts only a bare RG ID -- giraffe emits "@RG ID:<s> SM:<s>".
  # samtools addreplacerg -w overwrites that with the complete read group,
  # restoring LB and PL:ILLUMINA (see the "\\t" note on the command above).
  sample_name:
    type: string
    default: sample

outputs:
  aligned_reads_sorted:
    type: File
    outputBinding:
      glob: $(inputs.aligned_reads.nameroot).sorted.cram

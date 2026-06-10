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

# vg giraffe writes BAM to stdout. Capturing it with a bare CWL `stdout:` is
# fragile: vg can exit 0 yet leave a truncated/garbled BAM (e.g. killed
# mid-write, or a stray diagnostic line on stdout). Downstream the only symptom
# is samtools-sort dying three steps later with the cryptic
#   [E::aux_parse] unrecognized type 's' / samtools sort: truncated file
# because samtools is fed half a BAM. To fail loudly AT THE SOURCE we run vg
# under bash so we can (a) keep all of vg's progress/diagnostics on stderr where
# they can never contaminate the BAM stream, and (b) validate the captured file
# before this step is allowed to succeed.
#
# NOTE on CWL string interpolation in the script below:
#   * InlineJavascriptRequirement makes `$(...)` and `${...}` CWL expressions
#     EVERYWHERE in this scalar, so bash command substitution must use backticks
#     and bash variables must be `$name` (never `${name}`).
#   * A `\` immediately before a newline is treated as a CWL escape and silently
#     stripped, so do NOT use backslash line-continuations — the vg invocation is
#     kept on one logical line and statements are separated by real newlines.
#
# vg giraffe's --read-group takes ONLY the read-group ID string, NOT a full
# tab-delimited @RG line. A previous version passed
# "ID:<s>\tSM:<s>\tLB:<s>\tPL:ILLUMINA", so vg stored that entire tab-containing
# string as the RG ID and stamped it onto every read's RG:Z tag. When samtools
# later round-tripped the BAM through SAM text, the embedded tabs split RG:Z into
# extra columns and the leaked "SM:sample" was parsed as an aux field of type
# 's' -> "[E::aux_parse] unrecognized type 's' / samtools sort: truncated file",
# which is what crashed the downstream samtools-sort step. We now pass a bare ID
# (sample name); vg emits a clean "@RG ID:<sample> SM:<sample>".
baseCommand: bash
arguments:
  - -c
  - |
    set -euo pipefail

    out="$(inputs.bam_output)"

    # vg's progress (-p) and any warnings go to stderr (the job log); only the
    # BAM goes to "$out". Optional second read file is added only when provided.
    vg giraffe -p -t $(runtime.cores) -Z "$(inputs.graph.path)" --ref-paths "$(inputs.ref_paths.path)" -f "$(inputs.reads1.path)" $(inputs.reads2 ? '-f "' + inputs.reads2.path + '"' : '') -d "$(inputs.dist.path)" -m "$(inputs.min.path)" --output-format BAM --sample "$(inputs.sample_name)" --read-group "$(inputs.sample_name)" --rescue-algorithm none --max-dp-cells 4000000 > "$out"

    # Guard 1: vg must have produced a non-empty file.
    if [ ! -s "$out" ]; then
      echo "vg-giraffe-bam ERROR: vg giraffe produced an empty BAM ($out); it likely crashed before writing any output." >&2
      exit 1
    fi

    # Guard 2: a complete BGZF/BAM file ends with the 28-byte BGZF EOF marker
    # (this is exactly what `samtools quickcheck` verifies). Its absence means
    # the stream was truncated mid-write. We check it with coreutils so no
    # samtools dependency has to be added to the vg container.
    eof=`tail -c 28 "$out" | od -An -tx1 | tr -d ' \n'`
    want="1f8b08040000000000ff0600424302001b0003000000000000000000"
    if [ "$eof" != "$want" ]; then
      echo "vg-giraffe-bam ERROR: $out is missing the BGZF EOF marker -> the BAM is truncated/corrupt (vg giraffe likely died mid-write). Refusing to emit a bad BAM that would crash samtools-sort downstream." >&2
      exit 1
    fi

    echo "vg-giraffe-bam: $out passed BGZF EOF check (BAM is complete)." >&2

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
    type: File
    outputBinding:
      glob: $(inputs.bam_output)

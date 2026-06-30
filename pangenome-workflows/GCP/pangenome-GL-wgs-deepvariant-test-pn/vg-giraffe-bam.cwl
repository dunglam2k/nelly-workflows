cwlVersion: v1.1
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
  DockerRequirement:
    dockerPull: "quay.io/biocontainers/vg:1.54.0--h9ee0642_0"
  ResourceRequirement:
    coresMin: 10
    ramMin: $(64 * 1024)

# vg giraffe writes the BAM to stdout; CWL `stdout:` captures it to aligned.bam.
# vg's progress (-p) and warnings go to stderr (the job log), so they can never
# contaminate the BAM stream.
#
# --read-group takes ONLY the read-group ID string, NOT a full tab-delimited @RG
# line. An earlier version passed "ID:<s>\tSM:<s>\tLB:<s>\tPL:ILLUMINA"; vg stored
# that whole tab-containing string as the RG ID and stamped it onto every read, so
# when samtools later round-tripped through SAM text the embedded tabs split RG:Z
# into extra columns and the leaked "SM:sample" parsed as an aux field of type 's'
# -> "[E::aux_parse] unrecognized type 's' / samtools sort: truncated file", which
# crashed samtools-sort. We pass a bare ID (sample name); vg emits a clean
# "@RG ID:<sample> SM:<sample>".
#
# NOTE: a previous revision (fd19941) wrapped vg in `bash -c` and asserted the BAM
# ended in the exact 28-byte canonical htslib BGZF EOF marker. At WGS scale this
# fired as a FALSE POSITIVE: vg giraffe exits 0 after writing a complete BAM, but
# its stdout BAM does not terminate in that exact marker, so the assertion rejected
# a perfectly good BAM (disk had 100+ GB free -- not a truncation). samtools-sort
# tolerates a missing EOF marker (warns, does not crash) and rewrites a clean BAM/
# CRAM with a proper marker, so the guard was both unnecessary and wrong. Reverted
# to the proven stdout-capture form. (If a real integrity check is wanted later,
# run `samtools quickcheck` on the SORTED output in samtools-sort, where samtools
# is available and the BAM is guaranteed to carry htslib's EOF marker.)
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
- $(inputs.sample_name)
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

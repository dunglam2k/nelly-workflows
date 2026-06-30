cwlVersion: v1.1
class: CommandLineTool
# Drop every VCF record that falls inside an ExpansionHunter ReferenceRegion before
# phenotype prioritisation. DeepVariant systematically MIS-calls these short-tandem-
# repeat loci as coding frameshift indels -- e.g. a spurious ATXN3 chr14:92071010
# frameshift that Exomiser then scores pathogenic and ranks #1 in EVERY sample -- and
# the genuine expansion only appears as an unscorable symbolic <STR> allele. Both are
# noise to Exomiser. The authoritative repeat genotypes are carried separately to the
# genome-linter via eh_repeats.json, so nothing is lost.
#
# The exclusion BED is derived at run time from the EH VCF itself (POS..END per locus,
# padded), so it always matches the catalogue actually used. Note the CWL string-
# interpolation rules: genuine refs are $(inputs.*) / $(runtime.cores); literal tabs/
# newlines are \\t / \\n (single backslashes are stripped); awk's own $1/$2/$3 are not
# CWL expressions; no bash $()/${} and no backslash line-continuations.
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  DockerRequirement:
    dockerPull: "staphb/bcftools:1.19"
  ResourceRequirement:
    coresMin: 2
    ramMin: $(4 * 1024)
baseCommand: bash
arguments:
  - -c
  - |
    set -euo pipefail
    bcftools query -f '%CHROM\\t%POS\\t%INFO/END\\n' "$(inputs.eh_vcf.path)" | awk -v p=$(inputs.pad) 'BEGIN{OFS="\\t"} {s=$2-1-p; if(s<0)s=0; print $1, s, $3+p}' | sort -k1,1 -k2,2n > eh_regions.bed
    echo "exclude-eh-regions: excluding `wc -l < eh_regions.bed` EH repeat regions (pad=$(inputs.pad))" >&2
    bcftools view --threads $(runtime.cores) -T ^eh_regions.bed -Oz -o "$(inputs.output_name)" "$(inputs.input_vcf.path)"
    bcftools index --threads $(runtime.cores) -t "$(inputs.output_name)"

inputs:
  input_vcf:
    type: File
    secondaryFiles:
      - .tbi
  eh_vcf:
    # ExpansionHunter VCF (eh_repeats.vcf.gz); every record carries POS + INFO/END.
    type: File
    secondaryFiles:
      - .tbi
  pad:
    # Bases of padding on each side of an EH ReferenceRegion, to also catch a
    # repeat-indel that bcftools-norm left-aligned just outside the region.
    type: int
    default: 20
  output_name:
    type: string
    default: exomiser_input.vcf.gz

outputs:
  filtered_vcf:
    type: File
    secondaryFiles:
      - .tbi
    outputBinding:
      glob: $(inputs.output_name)

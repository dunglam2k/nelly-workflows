#!/bin/bash
# Self-contained Exomiser runner (lives inside the wrapper image, so it is NOT
# subject to CWL string interpolation). Args:
#   $1 data-dir  $2 vcf  $3 assembly(hg38|GRCh38)  $4 data-version  $5 HPO(csv)  $6 sex
set -euo pipefail
DATA="$1"; VCF="$2"; ASM="$3"; DV="$4"; HPO="${5:-}"; SEX="${6:-UNKNOWN}"

case "$ASM" in
  hg38|GRCh38) ASM=hg38; ASM_GRC=GRCh38 ;;
  hg19|GRCh37) ASM=hg19; ASM_GRC=GRCh37 ;;
  *) echo "exomiser: unknown assembly $ASM" >&2; exit 1 ;;
esac

# The data-directory must contain <dv>_<asm>/ and <dv>_phenotype/. Bundles
# uploaded to Keep with a top-level data/ prefix put them under $DATA/data/, so
# descend into it if that's where the assembly data actually lives.
if [ ! -d "$DATA/${DV}_$ASM" ] && [ -d "$DATA/data/${DV}_$ASM" ]; then
  DATA="$DATA/data"
fi
echo "exomiser: using data-directory $DATA" >&2
ls -la "$DATA" >&2 || true

# application.properties -> mounted Keep data bundle. (No variant-white-list-path:
# v2512 serves the ClinVar whitelist from the bundled <dv>_<asm>_clinvar.mv.db.)
{
  echo "exomiser.data-directory=$DATA"
  echo "exomiser.$ASM.data-version=$DV"
  echo "exomiser.phenotype.data-version=$DV"
} > application.properties

# Proband id MUST equal the VCF sample column or Exomiser aborts.
SAMPLE=$(zcat -f "$VCF" 2>/dev/null | grep -m1 '^#CHROM' | cut -f10 || true)
[ -z "$SAMPLE" ] && SAMPLE=proband

{
  echo "id: $SAMPLE"
  echo "subject:"
  echo "  id: $SAMPLE"
  echo "  sex: $SEX"
  echo "phenotypicFeatures:"
  IFS=','
  for t in $HPO; do
    t=$(echo "$t" | tr -d '[:space:]')
    [ -z "$t" ] && continue
    echo "  - type:"
    echo "      id: $t"
  done
  unset IFS
  echo "metaData:"
  echo "  created: '2024-01-01T00:00:00Z'"
  echo "  createdBy: nelly"
  echo "  phenopacketSchemaVersion: 1.0"
  echo "  resources:"
  echo "    - id: hp"
  echo "      name: human phenotype ontology"
  echo "      url: http://purl.obolibrary.org/obo/hp.owl"
  echo "      version: '2024-01-01'"
  echo "      namespacePrefix: HP"
  echo "      iriPrefix: 'http://purl.obolibrary.org/obo/HP_'"
} > phenopacket.yml

cat > analysis.yml <<'YML'
---
analysisMode: PASS_ONLY
inheritanceModes: {AUTOSOMAL_DOMINANT: 0.1, AUTOSOMAL_RECESSIVE_COMP_HET: 2.0, AUTOSOMAL_RECESSIVE_HOM_ALT: 0.1, X_DOMINANT: 0.1, X_RECESSIVE_COMP_HET: 2.0, X_RECESSIVE_HOM_ALT: 0.1, MITOCHONDRIAL: 0.2}
frequencySources: [UK10K, GNOMAD_E_AFR, GNOMAD_E_AMR, GNOMAD_E_EAS, GNOMAD_E_NFE, GNOMAD_E_SAS, GNOMAD_G_AFR, GNOMAD_G_AMR, GNOMAD_G_EAS, GNOMAD_G_NFE, GNOMAD_G_SAS]
pathogenicitySources: [REVEL, MVP, ALPHA_MISSENSE, SPLICE_AI]
steps: [failedVariantFilter: {}, variantEffectFilter: {remove: [FIVE_PRIME_UTR_EXON_VARIANT, FIVE_PRIME_UTR_INTRON_VARIANT, THREE_PRIME_UTR_EXON_VARIANT, THREE_PRIME_UTR_INTRON_VARIANT, NON_CODING_TRANSCRIPT_EXON_VARIANT, UPSTREAM_GENE_VARIANT, INTERGENIC_VARIANT, REGULATORY_REGION_VARIANT, CODING_TRANSCRIPT_INTRON_VARIANT, NON_CODING_TRANSCRIPT_INTRON_VARIANT, DOWNSTREAM_GENE_VARIANT]}, frequencyFilter: {maxFrequency: 2.0}, pathogenicityFilter: {keepNonPathogenic: true}, inheritanceFilter: {}, omimPrioritiser: {}, hiPhivePrioritiser: {}]
YML

echo "=== phenopacket.yml ==="; cat phenopacket.yml
echo "=== application.properties ==="; cat application.properties
java -Xmx28g -jar /exomiser/exomiser-cli-15.0.0.jar analyse \
  --sample phenopacket.yml --vcf "$VCF" --assembly "$ASM_GRC" \
  --analysis analysis.yml --output-directory results --output-filename exomiser \
  --output-format TSV_GENE,TSV_VARIANT,JSON,HTML
echo "=== results ==="; ls -la results/

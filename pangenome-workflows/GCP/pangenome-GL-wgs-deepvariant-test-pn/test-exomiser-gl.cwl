#!/usr/bin/env cwl-runner
# Standalone validation of the NEW annotation tail (exclude-eh-regions -> exomiser ->
# genome-linter-llm) on an already-produced normalized VCF + ExpansionHunter outputs, so
# we can test the Arvados deployment without rerunning the hours-long pangenome pipeline.
# Not part of the production workflow.
cwlVersion: v1.1
class: Workflow
inputs:
  exomiser_vcf: File           # normalized.vcf.gz (+ .tbi)
  eh_vcf: File                 # eh_repeats.vcf.gz (+ .tbi) -- defines the STR regions to drop
  eh_json: File                # eh_repeats.json -- authoritative repeat genotypes for the LLM
  exomiser_data: Directory
  hpo_terms: string
  phenotype:
    type: string
    default: ""
  sample_sex:
    type: string
    default: "UNKNOWN"
outputs:
  filtered_vcf:
    type: File
    outputSource: exclude-eh-regions/filtered_vcf
  genes_tsv:
    type: File
    outputSource: exomiser/exomiser_genes_tsv
  variants_tsv:
    type: File
    outputSource: exomiser/exomiser_variants_tsv
  exomiser_html:
    type: File
    outputSource: exomiser/exomiser_html
  genomelinter_output:
    type: File
    outputSource: genomelinter/genomelinter_output
steps:
  exclude-eh-regions:
    in:
      input_vcf: exomiser_vcf
      eh_vcf: eh_vcf
    out: [filtered_vcf]
    run: exclude-eh-regions.cwl
  exomiser:
    in:
      exomiser_vcf: exclude-eh-regions/filtered_vcf
      exomiser_data: exomiser_data
      hpo_terms: hpo_terms
      sample_sex: sample_sex
    out: [exomiser_genes_tsv, exomiser_variants_tsv, exomiser_json, exomiser_html]
    run: exomiser.cwl
  genomelinter:
    in:
      exomiser_genes_tsv: exomiser/exomiser_genes_tsv
      exomiser_variants_tsv: exomiser/exomiser_variants_tsv
      eh_json: eh_json
      phenotype: phenotype
    out: [genomelinter_output]
    run: genome-linter-llm.cwl

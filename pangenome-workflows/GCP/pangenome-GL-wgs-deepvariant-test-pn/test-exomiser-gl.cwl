#!/usr/bin/env cwl-runner
# Standalone validation of the two NEW steps (exomiser -> genome-linter-llm) on an
# already-produced normalized VCF, so we can test the Arvados deployment without
# rerunning the hours-long pangenome pipeline. Not part of the production workflow.
cwlVersion: v1.1
class: Workflow
inputs:
  exomiser_vcf: File
  exomiser_data: Directory
  hpo_terms: string
  phenotype:
    type: string
    default: ""
  sample_sex:
    type: string
    default: "UNKNOWN"
outputs:
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
  exomiser:
    in:
      exomiser_vcf: exomiser_vcf
      exomiser_data: exomiser_data
      hpo_terms: hpo_terms
      sample_sex: sample_sex
    out: [exomiser_genes_tsv, exomiser_variants_tsv, exomiser_json, exomiser_html]
    run: exomiser.cwl
  genomelinter:
    in:
      exomiser_genes_tsv: exomiser/exomiser_genes_tsv
      exomiser_variants_tsv: exomiser/exomiser_variants_tsv
      phenotype: phenotype
    out: [genomelinter_output]
    run: genome-linter-llm.cwl

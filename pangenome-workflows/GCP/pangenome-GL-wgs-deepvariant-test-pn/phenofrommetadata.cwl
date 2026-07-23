cwlVersion: v1.1
class: CommandLineTool
baseCommand:
  - python
  - patient_context.py
requirements:
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing:
      - entryname: patient_context.py
        entry:
          $include: patient_context.py
  DockerRequirement:
    dockerPull: 'dunglam2k/phenofrommetadata:v1.01'
inputs:
  metadata:
    type: File
    inputBinding:
      position: 1
  fallback_hpo_terms:
    # Compatibility for legacy Genoor metadata whose phenotype URIs are null.
    # Coded metadata always takes precedence over this value.
    type: string
    default: ""
    inputBinding:
      position: 2

outputs:
  pheno_output:
    type: string
    outputBinding:
      glob: phenofile.txt
      loadContents: true
      outputEval: |
        ${
          if (self.length === 0) {
            if (runtime.exitCode !== 0) return "";
            throw new Error("patient context output phenofile.txt is missing");
          }
          return self[0].contents.replace(/[\r\n]+$/, '');
        }
  hpo_terms:
    type: string
    outputBinding:
      glob: hpo_terms.txt
      loadContents: true
      outputEval: |
        ${
          if (self.length === 0) {
            if (runtime.exitCode !== 0) return "";
            throw new Error("patient context output hpo_terms.txt is missing");
          }
          return self[0].contents.replace(/[\r\n]+$/, '');
        }
  expansionhunter_sex:
    type: string
    outputBinding:
      glob: expansionhunter_sex.txt
      loadContents: true
      outputEval: |
        ${
          if (self.length === 0) {
            if (runtime.exitCode !== 0) return "";
            throw new Error("patient context output expansionhunter_sex.txt is missing");
          }
          return self[0].contents.replace(/[\r\n]+$/, '');
        }
  exomiser_sex:
    type: string
    outputBinding:
      glob: exomiser_sex.txt
      loadContents: true
      outputEval: |
        ${
          if (self.length === 0) {
            if (runtime.exitCode !== 0) return "";
            throw new Error("patient context output exomiser_sex.txt is missing");
          }
          return self[0].contents.replace(/[\r\n]+$/, '');
        }

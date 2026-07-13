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

outputs:
  pheno_output:
    type: string
    outputBinding:
      glob: phenofile.txt
      loadContents: true
      outputEval: ${ return self[0].contents.replace(/[\r\n]+$/, ''); }
  hpo_terms:
    type: string
    outputBinding:
      glob: hpo_terms.txt
      loadContents: true
      outputEval: ${ return self[0].contents.replace(/[\r\n]+$/, ''); }
  expansionhunter_sex:
    type: string
    outputBinding:
      glob: expansionhunter_sex.txt
      loadContents: true
      outputEval: ${ return self[0].contents.replace(/[\r\n]+$/, ''); }
  exomiser_sex:
    type: string
    outputBinding:
      glob: exomiser_sex.txt
      loadContents: true
      outputEval: ${ return self[0].contents.replace(/[\r\n]+$/, ''); }

cwlVersion: v1.1
class: CommandLineTool
baseCommand:
  - python
  - /app/phenofrommetadata.py
requirements:
  InlineJavascriptRequirement: {}
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
      outputEval: ${ return '\"' + self[0].contents + '\"'; }

stdout: phenofile.txt
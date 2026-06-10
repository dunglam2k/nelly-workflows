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
      # Return the raw phenotype string (trailing newline stripped). Do NOT wrap it
      # in literal double-quotes: the consumer (genome-linter) already passes it via
      # an env var, and the old '"' + contents + '"' wrapper combined with that
      # consumer's own quoting produced ""Chorea;Huntington disease"" — the ';' then
      # split the shell command, dropped the VCF arg and crashed the linter.
      outputEval: ${ return self[0].contents.replace(/[\r\n]+$/, ''); }

stdout: phenofile.txt
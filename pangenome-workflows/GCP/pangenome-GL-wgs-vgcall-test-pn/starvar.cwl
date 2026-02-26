cwlVersion: v1.1
class: CommandLineTool
baseCommand:
  - python
  - /starvar/STARVar.py
requirements:
  InitialWorkDirRequirement:
    listing:
      - entry: $(inputs.starvar_input_files)
        #writable: true
  InlineJavascriptRequirement: {}
  DockerRequirement:
    #dockerPull: 'dunglam2k/starvar:v1.04'
    #dockerPull: 'dunglam2k/starvar:v1.05'
    #dockerPull: 'dunglam2k/starvar:v1.06'
    #dockerPull: 'dunglam2k/starvar:v1.07'
    dockerPull: 'dunglam2k/starvar:v1.08'
  ResourceRequirement:
    #coresMin: 64
    #ramMin: $(160 * 1024)
    #coresMin: 4
    #ramMin: $(36 * 1024)
    coresMin: 10
    ramMin: $(44 * 1024)
  NetworkAccess:
    networkAccess: true
inputs:
  starvar_input:
    type: File
    inputBinding:
      position: 1
  starvar_option:
    type: string
    inputBinding:
      position: 2
  starvar_output_file:
    type: string
  starvar_pheno:
    type: string
    inputBinding:
      position: 3
  starvar_input_files:
    type:
      type: array
      items: File

outputs:
  starvar_output:
    type: File
    outputBinding:
      glob: $(inputs.starvar_output_file)

stdout: $(inputs.starvar_output_file)
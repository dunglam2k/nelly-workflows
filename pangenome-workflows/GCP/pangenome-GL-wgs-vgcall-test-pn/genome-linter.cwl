cwlVersion: v1.1
class: CommandLineTool
baseCommand:
  - python
  - /genome-linter/genome-linter/src/main.py
requirements:
  InlineJavascriptRequirement: {}
  ResourceRequirement:
    ramMin: $(1 * 1024)
    coresMin: 1
  NetworkAccess:
    networkAccess: true
  EnvVarRequirement:
    envDef:
      OPENROUTER_API_KEY: 'Enter your key'
  DockerRequirement:
    #dockerPull: 'dunglam2k/genome-linter:v1.0'
    dockerPull: 'dunglam2k/genome-linter:v1.01'
inputs:
  genomelinter_output_name:
    type: string
    default: "genomelinter-output.txt"
    inputBinding:
      prefix: --output
  genomelinter_model:
    type: string
    default: "deepseek/deepseek-chat-v3-0324:free"
    inputBinding:
      prefix: --openrouter_model
  genomelinter_phenotypes:
    type: string
    inputBinding:
      prefix: --phenotype
  genomelinter_input:
    type: File
    inputBinding:
      position: 1

outputs:
  genomelinter_output: 
    type: File
    outputBinding:
      glob:  $(inputs.genomelinter_output_name)
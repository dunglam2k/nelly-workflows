cwlVersion: v1.1
class: CommandLineTool
baseCommand: bash
requirements:
  InlineJavascriptRequirement: {}
  ShellCommandRequirement: {}
  ResourceRequirement:
    ramMin: $(1 * 1024)
    coresMin: 1
  NetworkAccess:
    networkAccess: true
  EnvVarRequirement:
    envDef:
      OPENROUTER_API_KEY: $(inputs.openrouter_api_key)
  DockerRequirement:
    #dockerPull: 'dunglam2k/genome-linter:v1.0'
    dockerPull: 'dunglam2k/genome-linter:v1.01'
arguments:
  - -c
  - |
    set -euo pipefail
    # genome-linter's main.py reads the VCF as plain text (open()/iterate), so a
    # bgzipped/gzipped VCF (e.g. the VEP output) makes it die with
    # "UnicodeDecodeError ... can't decode byte 0x8b". Decompress first.
    in="$(inputs.genomelinter_input.path)"
    case "$in" in
      *.gz) zcat "$in" > input.vcf ;;
      *) cp "$in" input.vcf ;;
    esac
    python /genome-linter/genome-linter/src/main.py --output "$(inputs.genomelinter_output_name)" --openrouter_model "$(inputs.genomelinter_model)" --phenotype "$(inputs.genomelinter_phenotypes)" input.vcf
inputs:
  openrouter_api_key:
    type: string
    default: ""
  genomelinter_output_name:
    type: string
    default: "genomelinter-output.txt"
  genomelinter_model:
    type: string
    default: "deepseek/deepseek-chat-v3-0324:free"
  genomelinter_phenotypes:
    type: string
  genomelinter_input:
    type: File

outputs:
  genomelinter_output:
    type: File
    outputBinding:
      glob: $(inputs.genomelinter_output_name)

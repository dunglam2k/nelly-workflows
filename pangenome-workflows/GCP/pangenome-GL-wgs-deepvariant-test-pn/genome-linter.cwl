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
      # Pass the phenotype, model and output name through the environment (CWL sets
      # these as literal values — no shell re-parsing) and reference them as
      # "$GL_*" below. This makes shell metacharacters in the phenotype label safe;
      # previously --phenotype "$(...)" with a ';' (e.g. "Chorea;Huntington disease")
      # split the command and crashed the linter.
      GL_PHENOTYPE: $(inputs.genomelinter_phenotypes)
      GL_MODEL: $(inputs.genomelinter_model)
      GL_OUTPUT: $(inputs.genomelinter_output_name)
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
    # Fail loudly if decompression yielded no variant records. Previously an empty
    # input.vcf was fed to the linter, which crashed -- yet the run still reported
    # green. A genome-linter failure must surface, not pass silently.
    if ! grep -qvE '^#' input.vcf; then
      echo "genome-linter: ERROR - input VCF contains no variant records" >&2
      exit 1
    fi
    python /genome-linter/genome-linter/src/main.py --output "$GL_OUTPUT" --openrouter_model "$GL_MODEL" --phenotype "$GL_PHENOTYPE" input.vcf
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

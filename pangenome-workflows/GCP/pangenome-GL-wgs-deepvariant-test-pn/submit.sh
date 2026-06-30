#!/usr/bin/env bash
# Submit a workflow to the cborg Arvados cluster with a dev/prod intermediate-output
# policy.
#
#   ./submit.sh dev  <workflow.cwl> <inputs.json> [name]   # keep intermediate step
#                                                          # outputs for debugging (default)
#   ./submit.sh prod <workflow.cwl> <inputs.json> [name]   # trash intermediate step
#                                                          # outputs on SUCCESS (declared
#                                                          # workflow outputs are kept)
#
# Rationale: each step writes its own Keep collection (CRAM, combined VCF, EH calls,
# normalized VCF, filtered VCF, Exomiser tables...). During development we want every
# intermediate to inspect; in production we only want the final declared outputs, and the
# rest cleaned up -- but ONLY if the run succeeded, so a failed run is still debuggable.
# Arvados' --trash-intermediate does exactly that (trash on success); --no-trash-intermediate
# (the default) keeps everything.
set -euo pipefail

MODE="${1:-dev}"; WF="${2:-}"; INPUTS="${3:-}"; NAME="${4:-}"
if [ -z "$WF" ] || [ -z "$INPUTS" ]; then
  echo "usage: $0 <dev|prod> <workflow.cwl> <inputs.json> [name]" >&2; exit 2
fi

case "$MODE" in
  dev)  TRASH=--no-trash-intermediate ;;
  prod) TRASH=--trash-intermediate ;;
  *) echo "mode must be 'dev' or 'prod', got '$MODE'" >&2; exit 2 ;;
esac
[ -z "$NAME" ] && NAME="$(basename "$WF" .cwl) ($MODE)"

export ARVADOS_API_HOST=cborg.projectnelly.com
ARVADOS_API_TOKEN=$(python -c "import configparser; c=configparser.ConfigParser(); c.read_string('[d]\n'+open('$HOME/.config/arvados/settings.conf').read()); print(c['d']['ARVADOS_API_TOKEN'])")
export ARVADOS_API_TOKEN

echo "submit: mode=$MODE ($TRASH) name='$NAME'" >&2
exec arvados-cwl-runner --submit --no-wait "$TRASH" --name "$NAME" "$WF" "$INPUTS"

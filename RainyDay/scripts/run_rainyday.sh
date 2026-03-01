#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Usage:
#   ./scripts/run_rainyday.sh [ENV_NAME] path/to/params.json
# If ENV_NAME is omitted it defaults to 'RainyDay_Env'.

ENV_NAME="${1:-RainyDay_Env}"
PARAM_FILE="${2:-}"

if [ -z "$PARAM_FILE" ]; then
  echo "Usage: $0 [ENV_NAME] path/to/params.json"
  echo "Example: $0 RainyDay_Env Examples/BigThompson/BigThompsonExample.json"
  exit 1
fi

# Initialize conda for this non-interactive shell.
# Prefer discovering the active conda base dynamically.
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
  if [ -n "$CONDA_BASE" ] && [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
  else
    eval "$(conda shell.bash hook 2>/dev/null)" || {
      echo "Failed to initialize conda from PATH."
      exit 1
    }
  fi
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/mambaforge/etc/profile.d/conda.sh" ]; then
  source "$HOME/mambaforge/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]; then
  source "$HOME/miniforge3/etc/profile.d/conda.sh"
elif [ -f "/opt/homebrew/Caskroom/miniforge/base/etc/profile.d/conda.sh" ]; then
  source "/opt/homebrew/Caskroom/miniforge/base/etc/profile.d/conda.sh"
else
  echo "conda not found. Please install Miniconda/Mambaforge/Miniforge or run 'conda init bash' and restart your shell."
  exit 1
fi

# Activate the environment
# Some conda activate hooks (e.g., GDAL) may reference unset variables.
# Temporarily disable nounset to avoid false failures during activation.
set +u
conda activate "$ENV_NAME" || {
  set -u
  echo "Failed to activate conda env '$ENV_NAME'. Make sure it exists (conda env list)."
  exit 1
}
set -u

# Run RainyDay (resolve path relative to this script, not caller CWD)
python "$REPO_ROOT/Source/RainyDay_Py3.py" "$PARAM_FILE"

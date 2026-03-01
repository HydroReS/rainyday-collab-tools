#!/usr/bin/env bash
#SBATCH --job-name=rainyday
#SBATCH --output=logs/rainyday_%j.out
#SBATCH --error=logs/rainyday_%j.err
#SBATCH --partition=main
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G

set -euo pipefail

# Amarel/Slurm launcher for RainyDay.
#
# Submit:
#   sbatch --export=ALL,PARAM_FILE=$PWD/Barbados_config_24h_fixed.json scripts/amarel_run_rainyday.sh
#
# Common overrides (examples):
#   sbatch --export=ALL,PARAM_FILE=/path/to/Barbados_config_24h_fixed.json scripts/amarel_run_rainyday.sh
#   sbatch --export=ALL,ENV_NAME=RainyDay_Env,PARAM_FILE=/path/to/config.json scripts/amarel_run_rainyday.sh
#
# Two-phase pattern (set booleans in JSON before each submission):
# - Phase 1: CREATECATALOG=true,  SCENARIOS=false
# - Phase 2: CREATECATALOG=false, SCENARIOS=true

SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prefer explicit REPO_ROOT, then SLURM_SUBMIT_DIR when it looks like repo root,
# otherwise fall back to script-relative resolution.
if [[ -n "${REPO_ROOT:-}" ]]; then
  REPO_ROOT="$REPO_ROOT"
elif [[ -n "${SLURM_SUBMIT_DIR:-}" && -f "${SLURM_SUBMIT_DIR}/Barbados_config_24h_fixed.json" ]]; then
  REPO_ROOT="$SLURM_SUBMIT_DIR"
else
  REPO_ROOT="$DEFAULT_REPO_ROOT"
fi

REPO_ROOT="$(realpath "$REPO_ROOT")"
RAINYDAY_ROOT="${RAINYDAY_ROOT:-$REPO_ROOT/RainyDay}"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

ENV_NAME="${ENV_NAME:-RainyDay_Env}"
PARAM_FILE="${PARAM_FILE:-}"
RAINYDAY_PY="$RAINYDAY_ROOT/Source/RainyDay_Py3.py"

init_conda() {
  if command -v conda >/dev/null 2>&1; then
    local conda_base
    conda_base="$(conda info --base 2>/dev/null || true)"
    if [[ -n "$conda_base" && -f "$conda_base/etc/profile.d/conda.sh" ]]; then
      source "$conda_base/etc/profile.d/conda.sh"
      return 0
    fi
    eval "$(conda shell.bash hook 2>/dev/null)" && return 0
  fi

  for candidate in \
    "$HOME/miniconda3/etc/profile.d/conda.sh" \
    "$HOME/mambaforge/etc/profile.d/conda.sh" \
    "$HOME/miniforge3/etc/profile.d/conda.sh"; do
    if [[ -f "$candidate" ]]; then
      source "$candidate"
      return 0
    fi
  done

  echo "ERROR: Could not initialize conda. Load Anaconda/Miniconda module first on Amarel."
  echo "Example: module purge && module load anaconda"
  exit 1
}

# Optional module load for HPC setups where conda is provided via modules
if command -v module >/dev/null 2>&1; then
  module purge >/dev/null 2>&1 || true
  module load anaconda >/dev/null 2>&1 || true
fi

init_conda

set +u
conda activate "$ENV_NAME" || {
  set -u
  echo "ERROR: Failed to activate conda env '$ENV_NAME'."
  exit 1
}
set -u

if [[ ! -f "$PARAM_FILE" ]]; then
  echo "ERROR: PARAM_FILE is required and must point to an existing JSON file."
  echo "Example submit: sbatch --export=ALL,PARAM_FILE=$REPO_ROOT/Barbados_config_24h_fixed.json scripts/amarel_run_rainyday.sh"
  echo "Current PARAM_FILE: ${PARAM_FILE:-<unset>}"
  exit 1
fi

if [[ ! -f "$RAINYDAY_PY" ]]; then
  echo "ERROR: RainyDay runner not found: $RAINYDAY_PY"
  exit 1
fi

echo "Running on host: $(hostname)"
echo "Conda env: $ENV_NAME"
echo "RainyDay root: $RAINYDAY_ROOT"
echo "Config: $PARAM_FILE"

python "$RAINYDAY_PY" "$PARAM_FILE"

#!/usr/bin/env bash
#SBATCH --job-name=imerg_download
#SBATCH --output=logs/imerg_download_%j.out
#SBATCH --error=logs/imerg_download_%j.err
#SBATCH --partition=main
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G

set -euo pipefail

# Amarel/Slurm launcher for IMERG download + preprocessing.
#
# Submit:
#   sbatch scripts/amarel_run_imerg_download.sh
#
# Common overrides (examples):
#   sbatch --export=ALL,START_DATE=2001-01-01,END_DATE=2003-12-31,REGION_NAME=Barbados scripts/amarel_run_imerg_download.sh
#   sbatch --export=ALL,LAT_MIN=8.0,LAT_MAX=20.0,LON_MIN=-68.0,LON_MAX=-55.0 scripts/amarel_run_imerg_download.sh
#
# Required on cluster:
# - A conda env with downloader deps, default name: IMERG_download_env
# - Valid NASA Earthdata ~/.netrc on the compute node filesystem

SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prefer explicit REPO_ROOT, then SLURM_SUBMIT_DIR when it looks like repo root,
# otherwise fall back to script-relative resolution.
if [[ -n "${REPO_ROOT:-}" ]]; then
  REPO_ROOT="$REPO_ROOT"
elif [[ -n "${SLURM_SUBMIT_DIR:-}" && -f "${SLURM_SUBMIT_DIR}/download_preprocess_IMERG_for_RainyDay.py" ]]; then
  REPO_ROOT="$SLURM_SUBMIT_DIR"
else
  REPO_ROOT="$DEFAULT_REPO_ROOT"
fi

REPO_ROOT="$(realpath "$REPO_ROOT")"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

ENV_NAME="${ENV_NAME:-IMERG_download_env}"
PY_SCRIPT="$REPO_ROOT/download_preprocess_IMERG_for_RainyDay.py"

START_DATE="${START_DATE:-}"
END_DATE="${END_DATE:-}"
REGION_NAME="${REGION_NAME:-}"
LAT_MIN="${LAT_MIN:-}"
LAT_MAX="${LAT_MAX:-}"
LON_MIN="${LON_MIN:-}"
LON_MAX="${LON_MAX:-}"
RAW_DIR="${RAW_DIR:-$REPO_ROOT/imerg/raw_hdf5}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/imerg/daily_nc}"
FAILED_LOG="${FAILED_LOG:-$OUTPUT_DIR/failed_dates.csv}"
RETRY_FAILED_CSV="${RETRY_FAILED_CSV:-}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

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

if [[ ! -f "$PY_SCRIPT" ]]; then
  echo "ERROR: Missing script: $PY_SCRIPT"
  exit 1
fi

mkdir -p "$RAW_DIR" "$OUTPUT_DIR"

cmd=(python "$PY_SCRIPT" --raw-dir "$RAW_DIR" --output-dir "$OUTPUT_DIR" --failed-log "$FAILED_LOG")

[[ -n "$START_DATE" ]] && cmd+=(--start-date "$START_DATE")
[[ -n "$END_DATE" ]] && cmd+=(--end-date "$END_DATE")
[[ -n "$REGION_NAME" ]] && cmd+=(--region-name "$REGION_NAME")
[[ -n "$LAT_MIN" ]] && cmd+=(--lat-min "$LAT_MIN")
[[ -n "$LAT_MAX" ]] && cmd+=(--lat-max "$LAT_MAX")
[[ -n "$LON_MIN" ]] && cmd+=(--lon-min "$LON_MIN")
[[ -n "$LON_MAX" ]] && cmd+=(--lon-max "$LON_MAX")
[[ -n "$RETRY_FAILED_CSV" ]] && cmd+=(--retry-failed-csv "$RETRY_FAILED_CSV")

if [[ -n "$EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  extra_array=($EXTRA_ARGS)
  cmd+=("${extra_array[@]}")
fi

echo "Running on host: $(hostname)"
echo "Conda env: $ENV_NAME"
echo "Command: ${cmd[*]}"
"${cmd[@]}"

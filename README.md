# RainyDay Collaboration Tools

This repository is a collaboration workspace for preparing and running RainyDay-related workflows (for example IMERG preprocessing, regional setup notes, and scenario/configuration files).

It includes:
- Setup and workflow notes (for example Barbados markdown guides)
- IMERG preprocessing script(s) and environment files
- Local data/configuration assets used for experiments
- A vendored `RainyDay/` directory with the RainyDay source and examples

## Important Status: Not Synced with Parent RainyDay Repository

> **Warning**
> This repository is **not automatically synced** with the parent/upstream RainyDay repository.
> The `RainyDay/` code and documentation here may differ from the latest upstream state.

## Potential Implications

Because this repo is not synced with upstream RainyDay, you should expect possible differences such as:
- Missing upstream bug fixes and new features
- Behavior differences versus current upstream documentation/examples
- Incompatibilities with newer configs, dependencies, or workflows
- Reproducibility drift when comparing results with teams using upstream RainyDay
- Extra merge effort when bringing in upstream updates later

## Recommended Practice

Before using this repo for production analyses or shared deliverables:
1. Compare this repository against the latest upstream RainyDay repository.
2. Decide whether to merge/cherry-pick upstream changes needed for your workflow.
3. Re-run validation checks after any sync/update.

## Repository Layout (Top Level)

- `RainyDay/`: Local RainyDay source, examples, and user guide
- `Barbados/`: Barbados GIS boundary files
- `imerg/`: Local IMERG working area
- `download_preprocess_IMERG_for_RainyDay.py`: IMERG download/preprocess pipeline
- `*_Setup.md`, `*_summary.md`, `*.json`, `*.yml`: Project notes and configuration assets

## Notes

- Paths and configs in this repository may be environment-specific.
- Validate local file paths, environments, and data availability before execution.

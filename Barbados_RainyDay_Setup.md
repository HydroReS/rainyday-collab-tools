# Setting Up RainyDay for Barbados using NASA IMERG

## Overview

Barbados is a small island (~430 km²) at approximately 13.1°N, 59.5°W. At IMERG's 0.1° resolution
(~11 km at the equator), the island spans roughly 4–5 grid cells in latitude and 3–4 in longitude.
This guide covers every step from data download to running RainyDay.

### Environment file note

- Use `RainyDay/RainyDay_Env.yml` to create the environment for running RainyDay (`Source/RainyDay_Py3.py`).
- Use `IMERG_download_env.yml` for the IMERG downloader/preprocessing script (`download_preprocess_IMERG_for_RainyDay.py`).
- `RainyDay/RainyDay.yml` is a legacy, heavily pinned environment and is generally not recommended for new setups.

---

## Step 1: Download NASA IMERG Data

**Recommended product:** GPM IMERG Final Run, Half-Hourly, V07
- Product ID: `GPM_3IMERGHH_07`
- Spatial resolution: 0.1° × 0.1°
- Temporal resolution: 30 minutes → 48 time steps per day
- Units: mm/hr (no conversion needed — RainyDay requires mm/hr)
- Coverage: 2000–present
- Source: [NASA GES DISC](https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHH_07/summary)

**Spatial extent to download (Eastern Caribbean transposition domain):**
```
Latitude:  8°N – 20°N
Longitude: 68°W – 55°W
```
Downloading only this region (not global) saves significant disk space.

**Access options:**
- **OPeNDAP** (recommended): returns NetCDF4 slices directly, no HDF5 conversion needed
- **earthaccess** Python library: programmatic download via NASA Earthdata
- **wget scripts**: generated from GES DISC data ordering

**Tip:** You need a free NASA Earthdata account at https://urs.earthdata.nasa.gov

---

## Step 2: Preprocess IMERG to RainyDay-Compatible NetCDF4

RainyDay has strict format requirements. IMERG data often needs preprocessing.

### 2a. Required output format per file (one file per day)

| Property | Requirement |
|----------|-------------|
| File format | NetCDF4 |
| Time steps per file | 48 (30-min × 48 = 1440 min/day — **required by RainyDay**) |
| Dimension order | `(time, latitude, longitude)` |
| Time variable name | **Must be `time`** (hardcoded in RainyDay) |
| Precipitation units | mm/hr (IMERG Final is already mm/hr ✓) |
| Lat/lon arrays | Must be **1D** regular grids |
| Longitude convention | Either 0–360 or -180–180 (RainyDay auto-converts) |

### 2b. Known IMERG format issues to fix

1. **Dimension order**: IMERG HDF5 files store precipitation as `[time, lon, lat]` — must be transposed to `[time, lat, lon]`
2. **Variable names**: In raw HDF5 the variable is at `/Grid/precipitationCal` — rename to something simpler (e.g. `precipitation`)
3. **Time variable name**: Ensure the time dimension is named `time` (not `Time` or `ntime`)
4. **Fill values**: Replace fill values (−9999.9) with NaN or a consistent fill

### 2c. Example preprocessing script (Python)

```python
import xarray as xr
import numpy as np
from pathlib import Path

def preprocess_imerg_daily(input_files_30min, output_file):
    """
    Concatenate 48 half-hourly IMERG files into one daily NetCDF4 file.
    input_files_30min: list of 48 NetCDF/HDF5 file paths for one day (sorted)
    output_file: output daily NetCDF4 path
    """
    ds = xr.open_mfdataset(
        input_files_30min,
        concat_dim="time",
        combine="nested",
        engine="netcdf4"   # or "h5netcdf" for HDF5
    )

    # Rename variables if needed
    if "precipitationCal" in ds:
        ds = ds.rename({"precipitationCal": "precipitation"})

    # Ensure dimension order is (time, lat, lon)
    ds["precipitation"] = ds["precipitation"].transpose("time", "lat", "lon")

    # Clip to Caribbean domain
    ds = ds.sel(lat=slice(8.0, 20.0), lon=slice(-68.0, -55.0))

    # Replace fill values
    ds["precipitation"] = ds["precipitation"].where(ds["precipitation"] >= 0, 0.0)

    # Write to daily NetCDF4
    ds.to_netcdf(output_file, format="NETCDF4")
    print(f"Written: {output_file}")
```

**Verify the output before running RainyDay:**
```python
import netCDF4 as nc
ds = nc.Dataset("IMERG_20050101.nc")
print(ds.variables.keys())      # should include: time, lat, lon, precipitation
print(ds["precipitation"].shape) # should be (48, ~120, ~130)
print(ds["precipitation"].units) # should be mm/hr
```

### 2d. Run the downloader script (recommended CLI usage)

From the project root:

```bash
# Show all available CLI options
python download_preprocess_IMERG_for_RainyDay.py --help

# Barbados example: run only 2001-01-01 to 2003-12-31
python download_preprocess_IMERG_for_RainyDay.py \
    --start-date 2001-01-01 \
    --end-date 2003-12-31 \
    --region-name Barbados \
    --lat-min 8.0 --lat-max 20.0 \
    --lon-min -68.0 --lon-max -55.0 \
    --raw-dir ./imerg/raw_hdf5 \
    --output-dir ./imerg/daily_nc \
    --failed-log ./imerg/daily_nc/failed_dates.csv
```

Optional flags:

```bash
# keep raw HDF5 granules
--keep-raw

# disable NetCDF compression (faster writes, larger files)
--no-compress

# choose compression strength (0-9)
--compression-level 4
```

Use this `RAINPATH` in your RainyDay JSON after preprocessing:

```json
"RAINPATH": "./imerg/daily_nc/IMERG_V07_Barbados_*.nc"
```

---

## Step 3: Create the Barbados Analysis Mask

You have two options:

### Option A: Use a Shapefile (recommended)
Create or download a Barbados polygon shapefile in WGS84 (EPSG:4326). Sources:
- GADM: https://gadm.org (country-level administrative boundaries)
- Natural Earth: https://naturalearthdata.com

Set in config:
```json
"POINTAREA": "basin",
"WATERSHEDSHP": "/path/to/barbados_boundary.shp"
```

### Option B: Use a Bounding Box
```json
"POINTAREA": "box",
"POINTBOUNDINGBOX": {
    "LATITUDE_MIN":  12.85,
    "LATITUDE_MAX":  13.40,
    "LONGITUDE_MIN": -59.70,
    "LONGITUDE_MAX": -59.38
}
```

> **Note on resolution**: At 0.1°, the island covers roughly 5 × 3 grid cells. The shapefile approach
> gives a more accurate mask; the bounding box approach will include some ocean cells around the island.

---

## Step 4: Define the Transposition Domain

The transposition domain must be:
1. **Meteorologically similar** to Barbados (tropical maritime, Caribbean)
2. **Large enough** to provide a sufficient sample of storms for the catalog
3. **Larger than the storm mask** (island bounding box) by at least several grid cells on each side

**Recommended domain — Eastern Caribbean:**
```json
"DOMAINTYPE": "rectangular",
"AREA_EXTENT": {
    "LATITUDE_MIN":  8.0,
    "LATITUDE_MAX":  20.0,
    "LONGITUDE_MIN": -68.0,
    "LONGITUDE_MAX": -55.0
}
```

This gives ~120 × 130 grid cells at 0.1° — large enough for meaningful SST statistics.

> **Alternatively**, use an irregular domain shapefile (DOMAINTYPE: "irregular") to exclude land areas
> and constrain transposition to ocean/island grid cells only, which may be more physically appropriate.

---

## Step 5: Create the JSON Configuration File

```json
{
    "MAINPATH":     "/path/to/output/Barbados_RainyDay",
    "SCENARIONAME": "Barbados_IMERG",

    "RAINPATH":     "/path/to/imerg/daily/IMERG_*.nc",

    "DOMAINTYPE":   "rectangular",
    "AREA_EXTENT": {
        "LATITUDE_MIN":  8.0,
        "LATITUDE_MAX":  20.0,
        "LONGITUDE_MIN": -68.0,
        "LONGITUDE_MAX": -55.0
    },

    "POINTAREA":    "basin",
    "WATERSHEDSHP": "/path/to/barbados_boundary.shp",

    "VARIABLES": {
        "rainname": "precipitation",
        "latname":  "lat",
        "longname": "lon"
    },

    "CREATECATALOG":    true,
    "DURATION":         24,
    "NSTORMS":          100,
    "TIMESEPARATION":   48,

    "SCENARIOS":        true,
    "NREALIZATIONS":    10,
    "NYEARS":           100,
    "NPERYEAR":         1,

    "TRANSPOSITION":    "nonuniform",

    "RESAMPLING":       "poisson",
    "CALCTYPE":         "ams",
    "RETURNLEVELS":     [2, 5, 10, 25, 50, 100, 200, 500],

    "DIAGNOSTICPLOTS":  true
}
```

### Key parameter choices explained

| Parameter | Value | Reason |
|-----------|-------|--------|
| `DURATION` | 24 | Captures both convective and synoptic-scale Caribbean events; start here |
| `NSTORMS` | 100 | Top 100 events in the catalog; adjust based on record length |
| `TIMESEPARATION` | 48 | 48 hours minimum between catalog storms to ensure independence |
| `TRANSPOSITION` | nonuniform | Weights placement by historical storm frequency — reduces near-zero rainfall events |
| `NREALIZATIONS` × `NYEARS` | 10 × 100 | 1,000 output scenario files; scale up once pipeline is validated |
| `NPERYEAR` | 1 | One storm per synthetic year (the largest) |

---

## Step 6: Run RainyDay

Quick run command using the provided fixed-duration config file:

```bash
./scripts/run_rainyday.sh RainyDay_Env /Users/thymios/Downloads/Temp/RainyDay/Barbados_config_24h_fixed.json
```

### Two-phase execution

Using `Barbados_config_24h_fixed.json`, run in two passes by changing only `CREATECATALOG` and `SCENARIOS`:

```bash
# Phase 1: set CREATECATALOG="true", SCENARIOS="false" in Barbados_config_24h_fixed.json
./scripts/run_rainyday.sh RainyDay_Env /Users/thymios/Downloads/Temp/RainyDay/Barbados_config_24h_fixed.json

# Phase 2: set CREATECATALOG="false", SCENARIOS="true" in Barbados_config_24h_fixed.json
./scripts/run_rainyday.sh RainyDay_Env /Users/thymios/Downloads/Temp/RainyDay/Barbados_config_24h_fixed.json
```

**Phase 1 — Build the catalog (run once):**
```json
"CREATECATALOG": true,
"SCENARIOS":     false
```
```bash
./scripts/run_rainyday.sh RainyDay_Env /path/to/Barbados_config.json
```
Check the catalog output and diagnostic plots before proceeding.

**Phase 2 — Generate scenarios (after validating the catalog):**
```json
"CREATECATALOG": false,
"SCENARIOS":     true
```
```bash
./scripts/run_rainyday.sh RainyDay_Env /path/to/Barbados_config.json
```

---

## Step 7: Check Outputs

```
MAINPATH/
├── Barbados_IMERG_catalog.nc          ← Storm catalog (100 storms)
├── Barbados_IMERG_FreqAnalysis.csv    ← Return period table
├── Barbados_IMERG_FrequencyAnalysis.png
└── Realizations/
    ├── realization1/
    │   ├── scenario_Barbados_IMERG_rlz1year1storm1.nc   ← [48, ~5, ~4] mm/hr
    │   ├── scenario_Barbados_IMERG_rlz1year2storm1.nc
    │   └── ...
    └── ...
```

Each scenario NetCDF contains:
- `rain[time, latitude, longitude]` — mm/hr over the Barbados bounding box
- 48 × 30-min time steps (one full day)
- Same spatial resolution as input IMERG (0.1°)

---

## Known Constraints and Potential Issues

| Issue | Detail | Solution |
|-------|--------|----------|
| **HDF5 not supported** | RainyDay reads NetCDF4 only | Convert IMERG HDF5 to NetCDF4 during preprocessing |
| **Time variable name** | Must be named `time` (hardcoded) | Rename during preprocessing if different |
| **Units must be mm/hr** | No auto-conversion | IMERG Final is already mm/hr ✓ |
| **Daily files required** | 48 time steps × 30 min = 1440 min | Concatenate 48 half-hourly files per day |
| **Island is very small** | ~5×3 grid cells at 0.1° | Ensure transposition domain has sufficient buffer |
| **Near-zero rainfall events** | Storms transposed far from Barbados | Use `nonuniform` transposition to reduce this |
| **Dimension order** | RainyDay expects `(time, lat, lon)` | Transpose during preprocessing if `(time, lon, lat)` |

---

## Recommended Workflow Summary

```
1. Download IMERG Final Run HH data for Caribbean (8–20°N, 68–55°W), 2000–present
2. Preprocess: HDF5 → NetCDF4, concat to daily files, fix dimension order, check units
3. Create Barbados shapefile (WGS84)
4. Write JSON config
5. Run Phase 1: CREATECATALOG=true → inspect catalog plots
6. Run Phase 2: SCENARIOS=true → generate 1,000+ spatial rainfall fields
7. Post-process output NetCDFs as needed
```

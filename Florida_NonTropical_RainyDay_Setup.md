# RainyDay Setup: Non-Tropical Stochastic Storm Set for Florida

## Objective

Generate a stochastic set of non-tropical rainfall events covering the entire state of
Florida as input to a **distributed hydrologic model** estimating flood response across
all catchments in the state.

Florida (24°N–31°N, 80°W–87°W, ~170,000 km²) is well-suited for RainyDay — large enough
to avoid small-island limitations, and the SE United States provides a large
meteorologically homogeneous transposition domain.

---

## Key Design Challenges

### 1. RainyDay is designed for one watershed at a time

RainyDay optimises its storm catalog for a single POINTAREA. Using Florida's full state
boundary as the POINTAREA means the catalog is biased toward **large synoptic events that
maximise statewide total rainfall** — locally intense storms that drive flooding in a specific
sub-region (e.g. a squall line over Tampa Bay, an MCS over the Panhandle) may score lower
in the FFT search and not make the catalog, even though they are flood-generating events
for those catchments.

**Solution**: Run RainyDay **three times** with sub-regional POINTAREA definitions,
each optimised for the storm climatology relevant to that part of Florida. Each run
produces spatial fields covering the full state extent. The three scenario sets are
then merged into a single ensemble for the distributed model.

### 2. Duration does not cleanly separate storm types

A 24-hour duration catalog captures **both** MCS events (short intense cores that dominate
the 24-hour total) and frontal/synoptic events — they compete in the same catalog.
The duration parameter should be chosen based on **catchment response time**, not storm type:

| Basin type | Typical response time | Recommended DURATION |
| --- | --- | --- |
| Small urban catchment (<50 km²) | 1–6 hr | 6 hr |
| Medium basin (50–1,000 km²) | 6–24 hr | 12–24 hr |
| Large river basin (>1,000 km²) | 24–72 hr | 48–72 hr |
| St. Johns / Suwannee / Apalachicola | Days | 72 hr |

For a statewide distributed model covering all catchment sizes, consider running
**two separate duration catalogs**: 6 hr and 24 hr.

### 3. Tropical storm separation requires preprocessing

RainyDay has no storm-type filter. Excluding tropical events must be done by
pre-processing the precipitation data before building the catalog (see Step 3).

---

## Step 1: Choose Your Precipitation Dataset

| Property | AORC v1.1 | MRMS QPE |
| -------- | --------- | -------- |
| **Resolution** | ~4 km (1/40°) | ~1 km (0.01°) |
| **Temporal res.** | Hourly | 2-min native; hourly accumulations available |
| **Record length** | 1979–present (~45 years) | 2012–present (~13 years) |
| **Format** | NetCDF4 (CF-compliant) | GRIB2 → needs conversion |
| **Units** | kg m⁻² s⁻¹ → **must convert to mm/hr** (×3600) | mm/hr ✓ |
| **Gauge adjustment** | Yes (multi-source reanalysis) | Yes (real-time gauge merging) |
| **RainyDay examples** | ✓ Used in official examples | Not used in examples |
| **Source** | NCAR RDA / NOAA | NOAA MRMS archive / Iowa Mesonet |

### Recommendation

**Use AORC as the primary choice.** The 45-year record is critical for building a catalog
of rare non-tropical storms — 13 years of MRMS is too short for robust extreme-value
statistics at 100–500-year return periods.

**Use MRMS** only if spatial resolution is critical for small urban basins (<100 km²).
At native 0.01°, the SE US domain contains ~2.4 million grid cells — computationally
demanding. Resample to 0.05° before use.

**Pragmatic approach**: Build the storm catalog with AORC. If higher spatial resolution
is needed for downstream hydraulic modelling, MRMS can serve as a supplementary source,
though this requires workflow modifications outside of RainyDay.

---

## Step 2: Download the Precipitation Data

### AORC v1.1

- **Source:** NCAR Research Data Archive (RDA), dataset ds559.0 — [rda.ucar.edu/datasets/ds559.0](https://rda.ucar.edu/datasets/ds559.0/)
- **Access:** Free registration required
- **Files:** One NetCDF4 file per year, variable `APCP_surface`
- **Coverage:** Download for the full SE US domain (24–36°N, 95–75°W)

```bash
# Generate download script from NCAR RDA portal, then:
wget -r -np -nH --cut-dirs=3 -A "*.nc" \
  "https://rda.ucar.edu/data/ds559.0/..."
```

### MRMS QPE (if chosen)

- **Source:** Iowa Environmental Mesonet — [mesonet.agron.iastate.edu/MRMS](https://mesonet.agron.iastate.edu/MRMS/)
- **Product:** `MultiSensor_QPE_01H_Pass2` (hourly, gauge-adjusted)
- **Format:** GRIB2 per hour → needs concatenation and NetCDF4 conversion
- **Alternative:** NOAA NCEI MRMS archive for bulk historical downloads

---

## Step 3: Mask Out Tropical Storm Events (Critical Step)

This is the key step separating non-tropical from mixed catalogs.
RainyDay has no storm-type awareness — this must be done as preprocessing on the
precipitation data itself.

### 3a. Get tropical storm track data (IBTrACS)

```python
# Install tropycal — Python library for tropical cyclone data
pip install tropycal

import tropycal.tracks as tracks

# Load North Atlantic basin
basin = tracks.TrackDataset(basin='north_atlantic', source='ibtracs', include_btk=True)
```

### 3b. Identify dates when tropical storms influenced the SE US domain

```python
import numpy as np
import pandas as pd
from datetime import timedelta

# Transposition domain bounds
DOMAIN_LAT_MIN, DOMAIN_LAT_MAX = 24.0, 36.0
DOMAIN_LON_MIN, DOMAIN_LON_MAX = -95.0, -75.0

def storm_in_domain(storm, lat_min, lat_max, lon_min, lon_max):
    """Return timestamps when storm centre is inside domain at TS strength or above."""
    lats  = storm.dict['lat']
    lons  = storm.dict['lon']
    times = storm.dict['time']   # numpy datetime64 array
    winds = storm.dict['vmax']   # knots
    mask = (
        (lats >= lat_min) & (lats <= lat_max) &
        (lons >= lon_min) & (lons <= lon_max) &
        (winds >= 34)            # tropical storm threshold
    )
    return times[mask]

# Collect all hours to exclude (with 24-hour buffer either side)
exclude_dates = set()
BUFFER_HOURS  = 24

for stormid in basin.dict['year'].keys():
    try:
        storm    = basin.get_storm(stormid)
        hit_times = storm_in_domain(storm,
                                    DOMAIN_LAT_MIN, DOMAIN_LAT_MAX,
                                    DOMAIN_LON_MIN, DOMAIN_LON_MAX)
        for t in hit_times:
            for delta_h in range(-BUFFER_HOURS, BUFFER_HOURS + 1):
                exclude_dates.add(pd.Timestamp(t) + timedelta(hours=delta_h))
    except Exception:
        pass

print(f"Total hours to exclude: {len(exclude_dates)}")
```

### 3c. Zero out precipitation during tropical periods

```python
import xarray as xr

def mask_tropical_events(input_file, output_file, exclude_dates):
    """Zero out precipitation at all timestamps flagged as tropical-influenced."""
    ds       = xr.open_dataset(input_file)
    times_pd = pd.DatetimeIndex(ds.time.values)
    mask     = times_pd.floor('H').isin(exclude_dates)

    if mask.any():
        rain = ds['precipitation']
        ds['precipitation'] = rain.where(~xr.DataArray(mask, dims='time'), 0.0)
        print(f"  Zeroed {mask.sum()} of {len(mask)} time steps")

    ds.to_netcdf(output_file, format='NETCDF4')
    ds.close()
```

> **Belt-and-suspenders**: Also set `EXCLUDEMONTHS: [7, 8, 9]` in the RainyDay config
> to catch any residual tropical events not covered by IBTrACS masking.

---

## Step 4: Preprocess to RainyDay-Compatible NetCDF4

### AORC preprocessing

```python
import xarray as xr

def preprocess_aorc_annual(input_file, output_file, domain_bounds):
    """
    Prepare one annual AORC file for RainyDay:
      - Rename variable
      - Convert units: kg m⁻² s⁻¹ → mm hr⁻¹  (multiply by 3600)
      - Clip to SE US domain
      - Ensure dimension order (time, latitude, longitude)
    """
    lat_min, lat_max, lon_min, lon_max = domain_bounds
    ds = xr.open_dataset(input_file)

    if 'APCP_surface' in ds:
        ds = ds.rename({'APCP_surface': 'precipitation'})

    ds['precipitation'] = (ds['precipitation'] * 3600.0)
    ds['precipitation'].attrs['units'] = 'mm/hr'

    ds = ds.sel(latitude=slice(lat_min, lat_max),
                longitude=slice(lon_min, lon_max))

    ds['precipitation'] = ds['precipitation'].transpose(
        'time', 'latitude', 'longitude')
    ds['precipitation'] = ds['precipitation'].clip(min=0.0)

    ds.to_netcdf(output_file, format='NETCDF4')
    ds.close()

domain = (24.0, 36.0, -95.0, -75.0)
for year in range(1979, 2024):
    preprocess_aorc_annual(
        f"/raw/aorc/AORC_{year}.nc",
        f"/processed/AORC_masked_{year}.nc",
        domain
    )
```

### MRMS preprocessing (if chosen)

```python
import xarray as xr

def preprocess_mrms_daily(grib2_files_hourly, output_file, domain_bounds):
    """Concatenate 24 hourly MRMS GRIB2 files into one daily NetCDF4."""
    lat_min, lat_max, lon_min, lon_max = domain_bounds
    datasets = []
    for f in grib2_files_hourly:
        ds = xr.open_dataset(f, engine='cfgrib',
                              backend_kwargs={'filter_by_keys': {
                                  'typeOfLevel': 'surface', 'stepType': 'accum'}})
        ds = ds.rename({'unknown': 'precipitation'})
        ds['longitude'] = xr.where(ds.longitude > 180,
                                   ds.longitude - 360, ds.longitude)
        ds = ds.sel(latitude=slice(lat_max, lat_min),   # MRMS is N→S
                    longitude=slice(lon_min, lon_max))
        datasets.append(ds)

    daily = xr.concat(datasets, dim='time')
    # MRMS is already mm/hr — no unit conversion needed
    # Optional: coarsen to reduce file size
    # daily = daily.coarsen(latitude=5, longitude=5, boundary='trim').mean()
    daily.to_netcdf(output_file, format='NETCDF4')
```

---

## Step 5: Define Florida Analysis Regions (Three Sub-Regional Runs)

Rather than one statewide catalog, run RainyDay three times to avoid catalog bias
toward large synoptic events and ensure locally intense sub-regional storms are
well-represented:

| Run | POINTAREA shapefile | Dominant non-tropical storm types |
| --- | ------------------- | ---------------------------------- |
| **North FL / Panhandle** | NW Florida basins | Frontal systems, extratropical cyclones |
| **Central Florida** | Central FL basins | MCS, sea-breeze, frontal |
| **South Florida** | South FL basins | MCS, convective lines, late-season fronts |

All three runs use the **same transposition domain** (SE US) and produce spatial fields
covering the full Florida bounding box — ensuring consistency for the distributed model.

**Sources for shapefiles:**

- US Census TIGER/Line: [census.gov/cgi-bin/geo/shapefiles](https://www.census.gov/cgi-bin/geo/shapefiles)
- Florida DEP GIS: [geodata.dep.state.fl.us](https://geodata.dep.state.fl.us)
- USGS NHD watershed boundaries: [usgs.gov/national-hydrography](https://www.usgs.gov/national-hydrography)

---

## Step 6: Define the Transposition Domain

Same domain for all three runs:

```json
"DOMAINTYPE": "rectangular",
"AREA_EXTENT": {
    "LATITUDE_MIN":  24.0,
    "LATITUDE_MAX":  36.0,
    "LONGITUDE_MIN": -95.0,
    "LONGITUDE_MAX": -75.0
}
```

This covers Florida + Georgia, Alabama, Mississippi, Louisiana, South Carolina, Tennessee —
a climatologically coherent humid subtropical region (~1,320 × 2,000 km).

**Optional**: use an irregular domain shapefile to restrict transposition to land areas
only, which may be more physically appropriate for non-tropical storms that interact
strongly with land surface.

---

## Step 7: JSON Configuration

Template for each of the three sub-regional runs (change POINTAREA per run):

```json
{
    "MAINPATH":     "/path/to/output/Florida_NonTropical_NorthFL",
    "SCENARIONAME": "FL_NonTropical_NorthFL",

    "RAINPATH":     "/path/to/processed/AORC_masked_*.nc",

    "DOMAINTYPE":   "rectangular",
    "AREA_EXTENT": {
        "LATITUDE_MIN":  24.0,
        "LATITUDE_MAX":  36.0,
        "LONGITUDE_MIN": -95.0,
        "LONGITUDE_MAX": -75.0
    },

    "POINTAREA":    "basin",
    "WATERSHEDSHP": "/path/to/north_florida_basins.shp",

    "VARIABLES": {
        "rainname": "precipitation",
        "latname":  "latitude",
        "longname": "longitude"
    },

    "CREATECATALOG":  true,
    "DURATION":       24,
    "NSTORMS":        100,
    "TIMESEPARATION": 72,

    "SCENARIOS":      true,
    "NREALIZATIONS":  50,
    "NYEARS":         500,
    "NPERYEAR":       1,

    "TRANSPOSITION":  "nonuniform",

    "RESAMPLING":     "poisson",
    "CALCTYPE":       "ams",
    "RETURNLEVELS":   [2, 5, 10, 25, 50, 100, 200, 500],

    "EXCLUDEMONTHS":  [7, 8, 9],

    "DIAGNOSTICPLOTS": true
}
```

### Parameter choices explained

| Parameter | Value | Reason |
|-----------|-------|--------|
| `DURATION` | 24 hr | Primary duration; also run 6 hr for small urban basins and 72 hr for large river basins |
| `NSTORMS` | 100 | ~2.2 events/year from 45-yr AORC record |
| `TIMESEPARATION` | 72 hr | 3 days ensures frontal system events are treated independently |
| `TRANSPOSITION` | nonuniform | Essential at this scale — weights by historical storm frequency |
| `EXCLUDEMONTHS` | [7,8,9] | Supplements IBTrACS masking for residual tropical events |
| `NREALIZATIONS × NYEARS` | 50 × 500 | 25,000 events per run — sufficient for 500-yr flood estimates |

---

## Step 8: How Many Scenarios Are Needed?

For flood frequency curves across all Florida catchments, required events depend on the
rarest return period targeted:

| Target return period | Minimum events (rule of thumb) |
| --- | --- |
| 100-year | ~10,000 |
| 500-year | ~50,000 |
| 1,000-year | ~100,000 |

**50 realizations × 500 years = 25,000 events per sub-region** is a practical starting
point for 500-year estimates. Scale up to 50,000+ for 1,000-year targets.

---

## Step 9: Output Volume Planning

Florida bounding box at AORC resolution (~4 km, 1/40°):

```
Grid size:          ~260 lat × 300 lon = 78,000 cells
Per-event file:     24 timesteps × 78,000 cells × 4 bytes ≈ 7.5 MB
25,000 events:      ~188 GB per sub-regional run
3 sub-regional runs: ~560 GB total
```

**I/O performance warning**: Reading 25,000 individual NetCDF files in a distributed
model is very slow. Plan a post-processing consolidation step before running the
hydrologic model:

```python
import xarray as xr
import glob

# Consolidate all scenario files into a single zarr store
files = sorted(glob.glob("/output/Realizations/**/scenario_*.nc", recursive=True))
ds    = xr.open_mfdataset(files, concat_dim='event', combine='nested')
ds.to_zarr("/output/FL_NonTropical_NorthFL_all_events.zarr")
```

---

## Step 10: Run RainyDay

### Phase 1 — Build and validate each sub-regional catalog

```json
"CREATECATALOG": true,
"SCENARIOS":     false
```

```bash
./scripts/run_rainyday.sh RainyDay_Env /path/to/Florida_NorthFL_config.json
./scripts/run_rainyday.sh RainyDay_Env /path/to/Florida_CentralFL_config.json
./scripts/run_rainyday.sh RainyDay_Env /path/to/Florida_SouthFL_config.json
```

**Validate each catalog before generating scenarios:**

- Storm dates predominantly in Nov–May? (expected for non-tropical)
- Storm locations distributed across the SE US domain?
- No obviously tropical-looking events (circular symmetric patterns)?
- Catalog max values physically plausible for the region?

### Phase 2 — Generate scenarios

```json
"CREATECATALOG": false,
"SCENARIOS":     true
```

Run each sub-region independently (parallelise across HPC nodes if available).

---

## Step 11: Expected Output Structure

```
Florida_NonTropical_NorthFL/       Florida_NonTropical_CentralFL/    Florida_NonTropical_SouthFL/
├── *_catalog.nc                   ├── *_catalog.nc                  ├── *_catalog.nc
├── *_FreqAnalysis.csv             ├── *_FreqAnalysis.csv            ├── *_FreqAnalysis.csv
└── Realizations/                  └── Realizations/                 └── Realizations/
    ├── realization1/                  ├── realization1/                 ├── realization1/
    │   ├── scenario_*_rlz1yr1.nc      │   └── ...                       │   └── ...
    │   └── ... (500 files)
    └── ... (50 realizations)
                                   ↓  Post-process & consolidate
                              FL_all_events.zarr
                              (75,000 events × [24, ~260, ~300] mm/hr)
```

---

## AORC vs. MRMS Decision Summary

| Consideration | Favours AORC | Favours MRMS |
| --- | --- | --- |
| Record length for rare events | ✓ 45 years | ✗ 13 years |
| Spatial detail for small basins | ✗ 4 km | ✓ 1 km |
| Computational cost | ✓ Manageable | ✗ Very large at 0.01° |
| Format compatibility | ✓ Near-native NetCDF4 | ✗ GRIB2 conversion needed |
| Pre-2012 events | ✓ Available | ✗ Not available |
| Unit conversion needed | ✗ Yes (×3600) | ✓ Already mm/hr |

---

## Full Preprocessing Checklist

```
[ ] AORC annual files downloaded for 1979–present
[ ] IBTrACS tropical storm dates identified for SE US domain (24–36°N, 95–75°W)
[ ] Tropical periods zeroed out in all annual precipitation files
[ ] AORC units converted from kg/m²/s to mm/hr (×3600)
[ ] Files clipped to SE US domain
[ ] Time variable confirmed named 'time'
[ ] Dimension order confirmed as (time, latitude, longitude)
[ ] Three sub-regional shapefiles prepared in WGS84:
    [ ] North Florida / Panhandle basins
    [ ] Central Florida basins
    [ ] South Florida basins
[ ] Output spot-check: ds['precipitation'].shape == (8760, ~480, ~800) per annual file
[ ] Three JSON config files prepared (one per sub-region)
[ ] Storage capacity confirmed: ~560 GB for 3 runs × 25,000 events
```

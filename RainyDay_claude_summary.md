# RainyDay Codebase Summary

## What is RainyDay?

RainyDay is a **Python framework for generating extreme rainfall scenarios** using **Stochastic Storm Transposition (SST)**. It is used by hydrologists and engineers to assess rainfall-driven flood hazards in watersheds where observational records are too short to estimate rare events (e.g., 100-year or 500-year storms).

---

## Directory Structure

```
RainyDay/
├── Source/
│   ├── RainyDay_Py3.py                  ← Main entry point (3012 lines)
│   └── RainyDay_utilities_Py3/
│       └── RainyDay_functions.py        ← Core algorithms (2305 lines)
├── Examples/
│   ├── BigThompson/                     ← 72-hr watershed example
│   └── Madison/                         ← 24-hr grid-point example
├── UserGuide/
│   └── RainyDay_Tutorial.ipynb          ← Jupyter notebook tutorial
├── scripts/run_rainyday.sh              ← Shell execution wrapper
├── Dockerfile                           ← Docker containerization
├── RainyDay_Env.yml                     ← Conda environment (Python 3.8)
└── README.md / SIMPLE_RUN.md
```

---

## Execution

```bash
./scripts/run_rainyday.sh RainyDay_Env Examples/BigThompson/BigThompsonExample.json
# → activates conda env, runs: python Source/RainyDay_Py3.py <config.json>
```

Or via Docker:
```bash
docker run rainyday <config.json>
```

---

## Inputs

| Input | Format | Description |
|-------|--------|-------------|
| **Config file** | JSON | Controls all behavior (paths, duration, storms, resampling) |
| **Precipitation data** | NetCDF4 `[time, lat, lon]` | Gridded rainfall fields (AORC, TMPA, Stage IV) |
| **Domain boundary** | Shapefile (WGS84) | Transposition domain and/or watershed outline |
| **IDF data** | Tab-separated text | Return period reference curves (optional validation) |
| **Intensity PDF** | Binary file | Pre-computed spatial rainfall distributions (optional) |

**Key JSON config parameters:**

```json
{
  "MAINPATH": "/output/directory",
  "RAINPATH": "/data/precip/*.nc",
  "DURATION": 72,           // storm duration in hours
  "NSTORMS": 100,           // top N storms to catalog
  "NYEARS": 100,            // synthetic years per realization
  "NREALIZATIONS": 100,     // independent Monte Carlo runs
  "RESAMPLING": "poisson",  // storm frequency model
  "TRANSPOSITION": "uniform",
  "CALCTYPE": "ams",        // Annual Max Series or pds
  "RETURNLEVELS": [2,5,10,25,50,100,200,500]
}
```

---

## Core Workflow

```
JSON Config
    ↓
Step 1: BUILD STORM CATALOG
  - Read NetCDF precipitation files
  - For each time window (duration hours):
      → FFT-based 2D convolution to find max rainfall region
      → If above threshold & separated in time: add to catalog
  → Output: NetCDF catalog (rainfall fields + locations + timestamps)
    ↓
Step 2: STOCHASTIC STORM TRANSPOSITION
  - For each of NREALIZATIONS × NYEARS:
      → Randomly select a storm from catalog
      → Randomly pick a transposition location (uniform or KDE-weighted)
      → Extract rainfall at that location
      → Optionally rescale intensity (stochastic/deterministic log-normal)
  → Output: NetCDF synthetic scenario files
    ↓
Step 3: FREQUENCY ANALYSIS
  - Aggregate rainfall over POINTAREA (watershed / grid cell / box)
  - Extract annual maxima (AMS) or threshold exceedances (PDS)
  - Fit Gumbel/GEV extreme value distribution
  - Calculate return period rainfalls with confidence intervals
  → Output: CSV (return period vs. rainfall depth)
    ↓
Step 4: DIAGNOSTIC PLOTS (optional)
  → Storm maps, hyetographs, CDFs (PNG via Cartopy/Matplotlib)
```

---

## Outputs

| Output | Format | Description |
|--------|--------|-------------|
| **Storm catalog** | NetCDF | Top N storms with rainfall fields, locations, times |
| **Synthetic scenarios** | NetCDF | Transposed rainfall fields per realization/year |
| **Frequency analysis** | CSV | Return periods → rainfall depths (+ 5th/95th percentile) |
| **Diagnostic plots** | PNG | Storm maps, hyetographs, catalog statistics |

Example CSV output:
```
Return Period, Precipitation, q5,   q95
2,             45.2,          42.1, 48.5
10,            65.3,          60.2, 71.1
100,           95.8,          85.4, 110.2
```

---

## Key Algorithms

**1. Storm Detection (`catalogFFT_irregular`)** — Slides a storm-shaped mask over the precipitation field using FFT-based convolution to efficiently find the grid location with maximum accumulated rainfall over each duration window.

**2. Stochastic Storm Transposition (`SSTalt`)** — Resamples and moves catalog storms to random locations within the transposition domain. Locations can be uniform or weighted by a kernel density estimate of historical storm frequencies.

**3. Intensity Rescaling (`ENHANCEDSST`)** — Applies a spatially-varying log-normal multiplier to account for climatological differences between a storm's origin location and its transposed location. Stochastic mode draws random multipliers; deterministic uses the median.

**4. Frequency Analysis** — Aggregates synthetic maxima, fits an extreme value distribution (Gumbel/GEV), and produces return-level estimates with bootstrap confidence intervals.

---

## Tech Stack

| Category | Libraries |
|----------|-----------|
| Core numerics | NumPy, SciPy, Numba (JIT) |
| Array/NetCDF I/O | xarray, NetCDF4 |
| GIS / spatial | Rasterio, Geopandas, Shapely, Cartopy |
| Stats / ML | scikit-learn (KDE bandwidth estimation) |
| Visualization | Matplotlib, Plotly |
| Infrastructure | Conda (Python 3.8), Docker, Dask |

---

## Two Worked Examples

| Example | Duration | Domain | Analysis | Purpose |
|---------|----------|--------|----------|---------|
| **BigThompson** | 72 hr | Irregular shapefile | Watershed AMS | Colorado flood hazard |
| **Madison** | 24 hr | Rectangular grid | PDS at single point | Wisconsin urban flooding |

---

## Source File Overview

The two source files contain essentially the entire logic; everything else is configuration, examples, and documentation.

- **`Source/RainyDay_Py3.py`** — Orchestration: config parsing, workflow control, output writing, diagnostic plots. Contains the `GriddedRainProperties` class for storing precipitation dataset metadata.
- **`Source/RainyDay_utilities_Py3/RainyDay_functions.py`** — Algorithms: catalog creation, transposition, intensity rescaling, frequency analysis, spatial utilities, NetCDF I/O.



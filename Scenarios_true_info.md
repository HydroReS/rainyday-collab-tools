# RainyDay: Generating Spatial Rainfall Fields with SCENARIOS=true

## What `SCENARIOS=true` Does

Setting `SCENARIOS=true` writes one NetCDF file **per transposed storm event** into a directory tree:

```
MAINPATH/
└── Realizations/
    ├── realization1/
    │   ├── scenario_{name}_rlz1year1storm1.nc
    │   ├── scenario_{name}_rlz1year2storm1.nc
    │   └── ...
    ├── realization2/
    │   └── ...
    └── ...
```

Each file contains the full **spatial rainfall field**:

```
Dimensions:  time × latitude × longitude
Variable:    rain  [mm hr⁻¹]
Metadata:    xlocation, ylocation (transposition point indices)
             original storm ID, year, realization ID
```

---

## Minimal Config for Spatial Field Output

```json
{
  "MAINPATH":       "/path/to/output",
  "SCENARIONAME":   "MyRun",
  "RAINPATH":       "/path/to/precip/*.nc",

  "CREATECATALOG":  true,
  "DURATION":       24,
  "NSTORMS":        100,

  "SCENARIOS":      true,
  "NREALIZATIONS":  10,
  "NYEARS":         100,
  "NPERYEAR":       1,

  "DOMAINTYPE":     "rectangular",
  "DOMAINSHP":      "/path/to/region.shp",

  "POINTAREA":      "grid",

  "VARIABLES": {
    "rainname": "precipitation",
    "latname":  "latitude",
    "longname": "longitude"
  }
}
```

**Key parameter decisions:**

| Parameter | Value | Why |
|-----------|-------|-----|
| `SCENARIOS` | `true` | Enables spatial field output |
| `POINTAREA` | `grid`, `basin`, `box`, or `point` | **Not** `pointlist` — that disables scenario output entirely |
| `NPERYEAR` | 1 (or more) | How many storms written per synthetic year |
| `FREQANALYSIS` | leave unset | Gets forced `true` anyway, but its CSV/PNG outputs are separate and don't affect your NetCDF files |

---

## Output Volume

Total files = `NREALIZATIONS × NYEARS × NPERYEAR`

With the example above (10 × 100 × 1 = **1,000 NetCDF files**). The code prints a speed warning but has no hard cap — watch disk space for large runs.

---

## What You Don't Need to Worry About

- The frequency analysis (CSV + plots) is computed as a side effect of `SCENARIOS=true` but is written to separate files — it does **not** alter the spatial NetCDF outputs.
- You can ignore `RETURNLEVELS`, `CALCTYPE`, and `RESAMPLING` parameters if you only care about the spatial rainfall fields.

---

## Transposition Options

| `TRANSPOSITION` | Behaviour |
|-----------------|-----------|
| `uniform` | Storms placed uniformly at random within domain |
| `nonuniform` | Kernel-density-weighted placement based on historical storm frequencies — more realistic spatial distribution |

For generating realistic event ensembles, `nonuniform` is generally the better choice.

---

## Notes on POINTAREA

The `POINTAREA` parameter controls the spatial aggregation used for frequency analysis. It also controls whether scenario files are written at all:

- `grid` — single grid cell
- `point` — nearest grid point to a lat/lon coordinate
- `box` / `rectangle` — rectangular sub-region
- `basin` / `watershed` — watershed polygon (requires shapefile)
- `pointlist` — **disables scenario output** (not supported with `SCENARIOS=true`)

---

## Important Behavioral Notes

- Setting `SCENARIOS=true` **automatically forces** `FREQANALYSIS=true` internally, regardless of what you set in the config.
- Before each run, existing scenario files in the output directory are **deleted** — back up previous runs if needed.
- Adding `PADSCENARIOS` (integer, default 0) appends extra time steps of zeros **after** each storm in the output files.

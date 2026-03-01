# RainyDay Storm Independence: Flowchart and Explanation

This document summarizes how RainyDay identifies and keeps **independent storms** when building a storm catalog.

## Flowchart

```mermaid
flowchart TD
    A[Read JSON settings: DURATION, TIMESEPARATION, DURATIONCORRECTION, NSTORMS] --> B[Set catduration]
    B --> B1{CreateCatalog and\nDURATIONCORRECTION=true?}
    B1 -- Yes --> B2[catduration = max(72h, 3 x DURATION)]
    B1 -- No --> B3[catduration = DURATION]

    B2 --> C[Compute effective time-separation window]
    B3 --> C

    C --> C1{DURATIONCORRECTION?}
    C1 -- No, TIMESEPARATION <= 0 --> C2[timeseparation = DURATION]
    C1 -- No, TIMESEPARATION > 0 --> C3[timeseparation = TIMESEPARATION + DURATION]
    C1 -- Yes --> C4[timeseparation = max(TIMESEPARATION + DURATION, catduration)]

    C2 --> D[Convert timeseparation to timedelta]
    C3 --> D
    C4 --> D

    D --> E[Loop through each input time step k]
    E --> F[Build rolling rainfall window ending at time k over catduration]
    F --> G[Sum rainfall over window]
    G --> H[Find max areal accumulation and location via FFT convolution with trimmask]

    H --> I{rainmax > weakest storm currently in catalog?}
    I -- No --> E
    I -- Yes --> J[checksep = current_time - each catalog storm end time]

    J --> K{Any checksep < timeseparation?}
    K -- No --> L[Independent in time: replace weakest catalog storm]
    K -- Yes --> M{rainmax >= close-storm intensity?}

    M -- No --> N[Discard candidate storm]
    M -- Yes --> O[Replace non-independent close storm(s) with stronger candidate]

    L --> E
    N --> E
    O --> E

    E --> P[After all files/timesteps: sort storms by intensity and write catalog]
```

## Key Interpretation

RainyDay enforces storm independence using a **minimum inter-event time** rule. For each candidate event, the code compares the candidate end time to end times of storms already in the catalog:

- If the candidate is too close in time to an existing catalog storm (`checksep < timeseparation`), it is treated as **non-independent**.
- In that non-independent case, the candidate is only kept if it is at least as strong as the close storm(s); otherwise it is discarded.
- If no existing storm is within the time-separation window, the candidate is considered independent and can enter the catalog if it beats the current weakest stored storm.

## What Controls Independence

- `DURATION` sets the analysis storm duration and contributes directly to the effective separation threshold.
- `TIMESEPARATION` is not always used directly:
  - if omitted or <= 0 and no duration correction, separation defaults to `DURATION`.
  - if provided and no duration correction, effective threshold is `TIMESEPARATION + DURATION`.
  - with duration correction, threshold is `max(TIMESEPARATION + DURATION, catduration)`.
- `DURATIONCORRECTION=true` typically increases both catalog window length (`catduration`) and the required event separation.
- `NSTORMS` controls catalog size (top-N retained), but independence filtering happens before final sorting/output.

## Practical Consequences

- Larger `TIMESEPARATION` (or larger `DURATION`) leads to stronger de-clustering and fewer near-duplicate storms.
- Smaller separation thresholds allow more temporally adjacent events into the top-N catalog.
- Spatial overlap is **not** the explicit independence criterion; the de-clustering decision is temporal.

## What Is Actually Stored Per Storm

When a storm candidate is accepted into the catalog, RainyDay stores a full 3D rainfall block for that storm:

- dimensions: `time x latitude x longitude`
- time axis: the selected window (`cattime[storm_num, :]`)
- rainfall array: `catrain` for that same selected window

The write call is in `RainyDay_Py3.py` (`RainyDay.writecatalog(...)`), and the file structure is defined in `RainyDay_functions.py` (`writecatalog`).

Important: for each storm file, the rainfall field (`rain`) is for that storm window, but some metadata arrays (`basinrainfall`, `xlocation`, `ylocation`, `cattime`) are written as full storm-dimension arrays.

## Example: DURATION = 24h, Real Storm Lasts 48h

### Case A: `DURATIONCORRECTION = false`

- During catalog creation, `catduration = DURATION = 24h`.
- The code scans with rolling 24h windows through time.
- Many overlapping 24h windows from the same 48h event can become candidates.
- Independence filtering (`checksep < timeseparation`) keeps only the strongest candidate among nearby windows.
- **Stored in catalog**: only the selected **24h** block (not the full 48h storm).

### Case B: `DURATIONCORRECTION = true`

- During catalog creation, `catduration = max(72h, 3 x DURATION)` (so for 24h, this is 72h).
- Candidate storms are selected based on this longer window context.
- **Stored in catalog**: a **72h** block per accepted storm.
- Later, when generating scenarios/statistics, the code applies rolling 24h sums within that longer block.

So the answer to your example is:

- If duration correction is off, you store a 24h slice (the best 24h window from that event).
- If duration correction is on, you store a longer event context (72h for a 24h duration setup), then evaluate 24h subwindows later.

## Source Locations

Primary implementation points:

- `RainyDay/Source/RainyDay_Py3.py`
  - parameter setup for `DURATION`, `DURATIONCORRECTION`, `TIMESEPARATION`
  - conversion to timedeltas and mask setup
  - main catalog loop with independence checks and replacement logic
- `RainyDay/Source/RainyDay_utilities_Py3/RainyDay_functions.py`
  - `catalogFFT_irregular(...)` for maximum areal accumulation search

## Recommended Parameter Sets

Use these settings depending on whether you want all saved events to have one fixed length, or to allow longer saved event windows.

### A) Fixed Event Duration (all saved events = `DURATION`)

Goal: if `DURATION = 24`, each saved catalog storm contains 24 hours.

Suggested parameters:

```json
{
  "CREATECATALOG": "true",
  "DURATION": 24,
  "DURATIONCORRECTION": "false",
  "TIMESEPARATION": 24,
  "NSTORMS": 100
}
```

Notes:

- With `DURATIONCORRECTION = "false"`, catalog duration is set equal to `DURATION`.
- Effective independence window becomes `TIMESEPARATION + DURATION` when `TIMESEPARATION > 0`.
- If you want the smallest allowed separation behavior, set `TIMESEPARATION` to `0` or omit it (effective separation defaults to `DURATION`).

### B) Varying/Extended Event Window (saved events can be longer than `DURATION`)

Goal: keep longer storm context in saved catalog files, while still analyzing a target duration (e.g., 24h).

Suggested parameters:

```json
{
  "CREATECATALOG": "true",
  "DURATION": 24,
  "DURATIONCORRECTION": "true",
  "TIMESEPARATION": 24,
  "NSTORMS": 100
}
```

What this does:

- Catalog window is `catduration = max(72, 3 x DURATION)`.
- For `DURATION = 24`, each saved storm window is 72h.
- The code later computes 24h rolling totals within those longer stored storms during scenario/statistical processing.

### Quick Decision Rule

- Want saved event files to always match `DURATION` exactly -> set `DURATIONCORRECTION` to `"false"`.
- Want saved files to include broader storm evolution around the peak period -> set `DURATIONCORRECTION` to `"true"`.

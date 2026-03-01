# How the Watershed / Region of Interest Affects RainyDay

## Two Separate Spatial Concepts

There are two independent spatial definitions in RainyDay that serve different purposes:

| Concept | Parameter | Role |
|---------|-----------|------|
| **Transposition domain** | `DOMAINSHP` / `AREA_EXTENT` | Where storms are *allowed to be placed* |
| **Analysis region** | `POINTAREA` / `WATERSHEDSHP` | Where rainfall is *extracted and measured* |

The only hard constraint between them is that the watershed must sit inside the transposition domain.

---

## How the Watershed Affects Each Step

### Step 1: Catalog Creation — watershed IS the search kernel

The FFT convolution in `catalogFFT_irregular` uses the **watershed shape as the convolution kernel**. The catalog does not find "storms with the highest global rainfall" — it finds **storms that maximise total rainfall integrated over the watershed shape**:

```
FFT result at position (x,y) = sum(rainfall[y:y+h, x:x+w] × watershed_mask)
```

The catalog stores the position that maximises this value for each storm event. This means a large storm slightly offset from the watershed could rank lower than a smaller storm perfectly centred on it.

---

### Step 2: Transposition — watershed does NOT constrain placement

During transposition, storms are placed randomly within the **transposition domain**, not forced onto the watershed. A storm can land anywhere in the domain, including locations that don't overlap the watershed at all — in which case the aggregated watershed rainfall is simply zero for that event.

The watershed bounding box (`maskheight × maskwidth`) defines the **size of the spatial window** extracted from the catalog storm at the transposed location — but the window can be placed anywhere in the domain.

---

### Step 3: Scenario output files — cropped to watershed bounding box

The output NetCDF spatial field is **not** the full transposition domain. It is cropped to the **bounding box of the watershed** (`subrangelat` / `subrangelon`). Every scenario file contains a rainfall field over a fixed window the size of the watershed's bounding box, regardless of where in the domain the storm was transposed.

---

## The Indirect "Focusing" Effect

The watershed does create an indirect bias toward watershed-relevant events, but not by constraining where storms land. The effect works through two mechanisms:

1. **Catalog is biased toward watershed-relevant storms** — only storms that produced high rainfall over the watershed region make it into the catalog.
2. **Nonuniform transposition** adds a second bias — storms are placed preferentially at locations with historically high storm frequency (KDE of catalog storm positions), which tend to cluster near the watershed area.

In practice, most transposed events will produce rainfall over the watershed — but this is a statistical tendency, not a hard constraint.

---

## The Three Internal Masks

| Mask | Definition | Purpose |
|------|-----------|---------|
| `trimmask` | Watershed shape, trimmed to bounding box | FFT convolution kernel; applied to extract watershed rainfall values |
| `catmask` | Full watershed mask on the original grid | Validation; ensures watershed is within transposition domain |
| `domainmask` | Transposition domain boundary | Prevents storms from being placed outside the domain |

---

## Practical Implication for Spatial Field Output

Since scenario output files are always cropped to the **watershed bounding box**, the watershed definition directly controls the spatial extent of every output NetCDF file. If you want larger spatial fields, define a larger watershed / analysis region, or be aware that the output window is fixed to the watershed bounding box regardless of where the storm is transposed within the domain.

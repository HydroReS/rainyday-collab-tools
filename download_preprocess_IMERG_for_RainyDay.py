"""
download_preprocess_IMERG_for_RainyDay.py
==========================================
Download NASA GPM IMERG Final Run Half-Hourly V07 data for any user-defined
domain and preprocess into RainyDay-compatible daily NetCDF4 files.

Each output file covers one calendar day (48 × 30-min timesteps) clipped to
the specified domain.

Requirements
------------
    pip install earthaccess h5py h5netcdf xarray netCDF4 numpy pandas tqdm

NASA Earthdata credentials
---------------------------
    Credentials are read from ~/.netrc.
    Register free at: https://urs.earthdata.nasa.gov
    Entry format in ~/.netrc:
        machine urs.earthdata.nasa.gov login <username> password <password>

RainyDay VARIABLES config for these output files
-------------------------------------------------
    "VARIABLES": {
        "rainname": "precipitation",
        "latname":  "latitude",
        "longname": "longitude"
    }
"""

import sys
import re
import time
import argparse
import h5py
import numpy as np
import pandas as pd
import xarray as xr
import netCDF4 as nc_lib
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import earthaccess


# ─── USER CONFIGURATION ───────────────────────────────────────────────────────

# A short name used as prefix for all output files, e.g. "Barbados", "Florida", "Jamaica"
REGION_NAME = "Barbados"

# Spatial domain to extract [degrees]
DOMAIN = {
    "lat_min":  11.0,
    "lat_max": 20.0,
    "lon_min": -69.0,
    "lon_max": -54.0,
}

# Date range to process (IMERG Final V07 available from June 2000)
START_DATE = datetime(2002, 7, 5)
END_DATE   = datetime(2002, 7, 8)

# Local directories
RAW_DIR    = Path("./imerg/raw_hdf5")   # Staging area for HDF5 files
OUTPUT_DIR = Path("./imerg/daily_nc")   # Destination for daily NetCDF4 files

# Set True to keep the raw HDF5 files after processing (~40 MB/day per granule × 48)
# Set False to delete them on-the-fly and only keep the processed NetCDF4 (~0.5 MB/day)
KEEP_RAW = True

# IMERG product identifiers on NASA GES DISC
IMERG_SHORTNAME = "GPM_3IMERGHH"
IMERG_VERSION   = "07"

# Download robustness controls
DOWNLOAD_RETRIES = 4
DOWNLOAD_BACKOFF_SECONDS = 5

# NetCDF output controls
ENABLE_NETCDF_COMPRESSION = True
NETCDF_COMPLEVEL = 4


# ─── AUTHENTICATION ───────────────────────────────────────────────────────────

def authenticate() -> None:
    """
    Authenticate with NASA Earthdata using credentials stored in ~/.netrc.
    """
    try:
        auth = earthaccess.login(strategy="netrc")
    except Exception as exc:
        sys.exit(
            "ERROR: NASA Earthdata authentication failed.\n"
            "Ensure ~/.netrc contains:\n"
            "  machine urs.earthdata.nasa.gov login <user> password <pass>\n"
            f"Details: {exc}"
        )

    if auth is None:
        sys.exit(
            "ERROR: NASA Earthdata authentication did not initialize.\n"
            "Check ~/.netrc and try logging in again."
        )

    print("NASA Earthdata authentication initialized.")


# ─── DOWNLOAD ONE DAY ─────────────────────────────────────────────────────────

def _granule_sort_key(filepath: Path):
    """
    Extract sortable timestamp key from IMERG filename.
    Typical IMERG filename includes fragments like: YYYYMMDD-SHHMMSS
    """
    match = re.search(r"(\d{8})-S(\d{6})", filepath.name)
    if match:
        return match.group(1), match.group(2)
    return filepath.name, ""


def download_day(date: datetime, staging_dir: Path) -> tuple:
    """
    Search and download all 48 IMERG half-hourly HDF5 files for one UTC date.

    Returns
    -------
    tuple[list[Path], str | None]
        (downloaded_files, error_message)
        error_message is None on success.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    day_start = date.strftime("%Y-%m-%dT00:00:00Z")
    day_end = date.strftime("%Y-%m-%dT23:59:59Z")

    results = earthaccess.search_data(
        short_name=IMERG_SHORTNAME,
        version=IMERG_VERSION,
        temporal=(day_start, day_end),
    )

    if not results:
        print(f"  WARNING: No IMERG files found for {date.date()}")
        return [], "No granules found"

    if len(results) != 48:
        print(f"  WARNING: Expected 48 granules for {date.date()}, found {len(results)}")

    downloaded = None
    last_error = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            downloaded = earthaccess.download(results, local_path=staging_dir)
            break
        except Exception as exc:
            last_error = str(exc)
            if attempt < DOWNLOAD_RETRIES:
                wait_seconds = DOWNLOAD_BACKOFF_SECONDS * (2 ** (attempt - 1))
                print(f"  Download retry {attempt}/{DOWNLOAD_RETRIES - 1} failed; waiting {wait_seconds}s...")
                time.sleep(wait_seconds)

    if downloaded is None:
        print("  Bulk download failed repeatedly; trying per-granule fallback...")
        fallback_paths = []
        for granule in results:
            granule_downloaded = None
            granule_error = None
            for attempt in range(1, DOWNLOAD_RETRIES + 1):
                try:
                    granule_downloaded = earthaccess.download([granule], local_path=staging_dir)
                    if granule_downloaded:
                        break
                except Exception as exc:
                    granule_error = str(exc)
                    if attempt < DOWNLOAD_RETRIES:
                        wait_seconds = DOWNLOAD_BACKOFF_SECONDS * (2 ** (attempt - 1))
                        time.sleep(wait_seconds)

            if not granule_downloaded:
                return [], (
                    "Download failed after retries (bulk + per-granule). "
                    f"Last error: {granule_error or last_error}"
                )

            fallback_paths.extend(Path(path) for path in granule_downloaded)

        downloaded_paths = sorted(fallback_paths, key=_granule_sort_key)
        return downloaded_paths, None

    downloaded_paths = [Path(f) for f in downloaded]
    downloaded_paths = sorted(downloaded_paths, key=_granule_sort_key)
    return downloaded_paths, None


# ─── READ ONE HDF5 GRANULE ────────────────────────────────────────────────────

def read_imerg_granule(filepath: Path, domain: dict) -> tuple:
    """
    Read one IMERG V07 half-hourly HDF5 file, clip to domain, and return arrays.

    IMERG V07 HDF5 structure (inside /Grid group):
        precipitation : (1, n_lat, n_lon)  [mm/hr]   ← V07 renamed from precipitationCal
        lat           : (n_lat,)            south → north, -89.95 to +89.95
        lon           : (n_lon,)            west  → east,  -179.95 to +179.95
        time          : (1,)                minutes since epoch (from .units attribute)

    Returns
    -------
    precip    : np.ndarray [n_lat_clip, n_lon_clip]  float32, mm/hr
    lat       : np.ndarray [n_lat_clip]              float32, degrees_north
    lon       : np.ndarray [n_lon_clip]              float32, degrees_east
    timestamp : np.datetime64                        granule start time (minute precision)
    """
    with h5py.File(filepath, "r") as f:
        grid = f["Grid"]

        # V07 uses "precipitation"; V06 used "precipitationCal" — handle both
        if "precipitation" in grid:
            precip_var = grid["precipitation"]
        elif "precipitationCal" in grid:
            precip_var = grid["precipitationCal"]
        else:
            raise KeyError(f"No precipitation variable found in {filepath.name}")

        precip_raw = precip_var[0, :, :].astype("float32")

        scale_factor = float(np.array(precip_var.attrs.get("scale_factor", 1.0)).squeeze())
        add_offset = float(np.array(precip_var.attrs.get("add_offset", 0.0)).squeeze())

        fill_value = precip_var.attrs.get("_FillValue", precip_var.attrs.get("missing_value", None))
        if fill_value is not None:
            fill_value = float(np.array(fill_value).squeeze())
            fill_mask = np.isclose(precip_raw, fill_value)
        else:
            fill_mask = np.zeros_like(precip_raw, dtype=bool)

        lat_all    = grid["lat"][:].astype("float32")   # (1800,) south→north
        lon_all    = grid["lon"][:].astype("float32")   # (3600,) west→east
        time_val   = float(grid["time"][0])
        time_units = grid["time"].attrs.get("units", b"").decode().strip()
        time_cal   = grid["time"].attrs.get("calendar", b"gregorian").decode()

    # IMERG HDF5 precipitation may be stored as (lon, lat); convert to (lat, lon)
    if precip_raw.shape == (lat_all.size, lon_all.size):
        pass
    elif precip_raw.shape == (lon_all.size, lat_all.size):
        precip_raw = precip_raw.T
        fill_mask = fill_mask.T
    else:
        raise ValueError(
            f"Unexpected precipitation shape {precip_raw.shape}; expected "
            f"(lat, lon)=({lat_all.size}, {lon_all.size}) or "
            f"(lon, lat)=({lon_all.size}, {lat_all.size})"
        )

    # Apply encoded scaling if present and clean invalid values
    precip_scaled = precip_raw * scale_factor + add_offset
    precip_scaled = np.where(fill_mask, np.nan, precip_scaled)
    precip_scaled = np.where(~np.isfinite(precip_scaled), np.nan, precip_scaled)

    # Replace missing/negative values with 0 (dry)
    precip_scaled = np.where(precip_scaled < 0.0, 0.0, precip_scaled)
    precip_scaled = np.nan_to_num(precip_scaled, nan=0.0).astype("float32")

    # Decode timestamp to numpy datetime64
    dt        = nc_lib.num2date(time_val, units=time_units, calendar=time_cal)
    timestamp = np.datetime64(dt.isoformat(), "m")

    # Spatial clip to domain
    lat_mask = (lat_all >= domain["lat_min"]) & (lat_all <= domain["lat_max"])
    lon_mask = (lon_all >= domain["lon_min"]) & (lon_all <= domain["lon_max"])
    lat      = lat_all[lat_mask]
    lon      = lon_all[lon_mask]
    precip   = precip_scaled[np.ix_(lat_mask, lon_mask)]

    return precip, lat, lon, timestamp


# ─── BUILD DAILY NETCDF4 ──────────────────────────────────────────────────────

def build_daily_netcdf(date: datetime, hdf5_files: list,
                       output_file: Path, domain: dict,
                       region_name: str,
                       compress_output: bool = ENABLE_NETCDF_COMPRESSION,
                       compression_level: int = NETCDF_COMPLEVEL) -> tuple:
    """
    Concatenate 48 half-hourly granules into one RainyDay-compatible daily NetCDF4 file.

    Output
    ------
    Dimensions : time=48, latitude, longitude
    Variable   : precipitation [mm/hr]  — shape (48, n_lat, n_lon)
    Time       : numpy datetime64[m] at 30-min intervals, variable named 'time'
    """
    if len(hdf5_files) != 48:
        print(f"  SKIP {date.date()}: need 48 files, have {len(hdf5_files)}")
        return False, f"Need 48 files, found {len(hdf5_files)}"

    all_precip = []
    all_times  = []

    for filepath in hdf5_files:
        try:
            precip, lat, lon, ts = read_imerg_granule(filepath, domain)
            all_precip.append(precip)
            all_times.append(ts)
        except Exception as e:
            print(f"  ERROR reading {filepath.name}: {e}")
            return False, f"Read error in {filepath.name}: {e}"

    precip_stack = np.stack(all_precip, axis=0)   # → (48, n_lat, n_lon)

    ds = xr.Dataset(
        {
            "precipitation": xr.DataArray(
                data=precip_stack,
                dims=["time", "latitude", "longitude"],
                attrs={
                    "units":         "mm/hr",
                    "long_name":     "Precipitation rate",
                    "standard_name": "precipitation_flux",
                    "source":        "GPM IMERG Final Run V07",
                },
            )
        },
        coords={
            "time": (
                "time",
                np.array(all_times, dtype="datetime64[m]"),
                {"long_name": "Time", "standard_name": "time"},
            ),
            "latitude": (
                "latitude",
                lat,
                {"units": "degrees_north", "long_name": "Latitude",
                 "standard_name": "latitude"},
            ),
            "longitude": (
                "longitude",
                lon,
                {"units": "degrees_east", "long_name": "Longitude",
                 "standard_name": "longitude"},
            ),
        },
        attrs={
            "title":       f"GPM IMERG V07 {region_name} — daily file for RainyDay",
            "history":     f"Created {datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')}",
            "conventions": "CF-1.8",
            "region":      region_name,
            "date":        date.strftime("%Y-%m-%d"),
            "domain":      (f"lat [{domain['lat_min']}, {domain['lat_max']}] "
                            f"lon [{domain['lon_min']}, {domain['lon_max']}]"),
            "rainyday_variables": (
                "rainname=precipitation, latname=latitude, longname=longitude"
            ),
        },
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if compress_output:
            encoding = {
                "precipitation": {
                    "zlib": True,
                    "complevel": compression_level,
                    "dtype": "float32",
                    "_FillValue": -9999.0,
                }
            }
            ds.to_netcdf(output_file, format="NETCDF4", encoding=encoding)
        else:
            ds.to_netcdf(output_file, format="NETCDF4")
    except Exception as exc:
        try:
            if output_file.exists():
                output_file.unlink()
        except Exception:
            pass
        ds.close()
        return False, f"Write error: {exc}"

    ds.close()
    return True, None


def is_valid_output_file(filepath: Path) -> bool:
    """Lightweight validation to avoid skipping corrupt/incomplete output files."""
    if not filepath.exists() or filepath.stat().st_size == 0:
        return False

    try:
        ds = xr.open_dataset(filepath)
        has_var = "precipitation" in ds.data_vars
        has_time = "time" in ds.sizes and ds.sizes.get("time", 0) == 48
        ds.close()
        return has_var and has_time
    except Exception:
        return False


# ─── VERIFICATION ────────────────────────────────────────────────────────────

def verify_file(filepath: Path, domain: dict) -> None:
    """
    Check a processed daily file against all RainyDay compatibility requirements.
    Prints a pass/fail report for each check.
    """
    ds = xr.open_dataset(filepath)

    print(f"\n── RainyDay compatibility check: {filepath.name} ──")

    has_precip = "precipitation" in ds.data_vars

    checks = {
        "Format is NetCDF4":
            filepath.suffix in (".nc", ".nc4"),
        "Variable 'precipitation' exists":
            has_precip,
        "Time variable named 'time'":
            "time" in ds.coords,
        "Latitude named 'latitude'":
            "latitude" in ds.coords,
        "Longitude named 'longitude'":
            "longitude" in ds.coords,
        "Dimension order (time, latitude, longitude)":
            (list(ds["precipitation"].dims) == ["time", "latitude", "longitude"]) if has_precip else False,
        "48 time steps (30-min × 48 = 1440 min/day)":
            ds.sizes["time"] == 48,
        "1D latitude array":
            ds["latitude"].ndim == 1,
        "1D longitude array":
            ds["longitude"].ndim == 1,
        "Units = mm/hr":
            (ds["precipitation"].attrs.get("units", "") == "mm/hr") if has_precip else False,
        "No negative precipitation values":
            (float(ds["precipitation"].min()) >= 0.0) if has_precip else False,
        "Latitude within domain bounds":
            (float(ds["latitude"].min()) >= domain["lat_min"] and
             float(ds["latitude"].max()) <= domain["lat_max"]),
        "Longitude within domain bounds":
            (float(ds["longitude"].min()) >= domain["lon_min"] and
             float(ds["longitude"].max()) <= domain["lon_max"]),
    }

    all_pass = True
    for description, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {description}")

    if has_precip:
        print(f"\n  Shape:       {ds['precipitation'].shape}")
        print(f"  Time:        {str(ds.time.values[0])} → {str(ds.time.values[-1])}")
        print(f"  Lat range:   {float(ds.latitude.min()):.2f} → {float(ds.latitude.max()):.2f}°N")
        print(f"  Lon range:   {float(ds.longitude.min()):.2f} → {float(ds.longitude.max()):.2f}°E")
        print(f"  Max precip:  {float(ds['precipitation'].max()):.2f} mm/hr")
    else:
        print("\n  Dataset has no 'precipitation' variable (file is likely corrupted/incomplete).")
    print(f"\n  {'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED — review output above'}")

    ds.close()


# ─── STORAGE ESTIMATE ────────────────────────────────────────────────────────

def print_storage_estimate(start: datetime, end: datetime,
                           domain: dict, keep_raw: bool) -> None:
    """Print an estimated storage breakdown before starting the download."""
    n_days     = (end - start).days + 1
    n_lat      = round((domain["lat_max"] - domain["lat_min"]) / 0.1) + 1
    n_lon      = round((domain["lon_max"] - domain["lon_min"]) / 0.1) + 1
    bytes_nc   = 48 * n_lat * n_lon * 4          # float32 per processed file
    bytes_hdf5 = 48 * 40 * 1024 * 1024           # ~40 MB per raw HDF5 granule

    print("\n── Storage estimate ──────────────────────────────────────────")
    print(f"  Date range:         {start.date()} → {end.date()}  ({n_days} days)")
    print(f"  Domain grid:        {n_lat} lat × {n_lon} lon")
    print(f"  Per-day NetCDF4:    ~{bytes_nc / 1e6:.1f} MB")
    print(f"  Total NetCDF4:      ~{n_days * bytes_nc / 1e9:.1f} GB")
    if keep_raw:
        print(f"  Per-day raw HDF5:   ~{bytes_hdf5 / 1e6:.0f} MB  (KEEP_RAW=True)")
        print(f"  Total raw HDF5:     ~{n_days * bytes_hdf5 / 1e9:.0f} GB")
    else:
        print(f"  Raw HDF5:           deleted after processing  (KEEP_RAW=False)")
    print("──────────────────────────────────────────────────────────────\n")


# ─── MAIN PROCESSING LOOP ────────────────────────────────────────────────────

def process_dates(dates,
                  raw_dir: Path, output_dir: Path,
                  domain: dict, region_name: str,
                  keep_raw: bool,
                  failed_log_file: Path | None = None,
                  compress_output: bool = ENABLE_NETCDF_COMPRESSION,
                  compression_level: int = NETCDF_COMPLEVEL) -> None:
    """
    Main loop: download and process provided dates.
    Automatically skips dates where the output file already exists,
    so interrupted runs can be safely resumed.
    """
    if len(dates) == 0:
        print("No dates to process.")
        return

    first_day = dates[0].date() if isinstance(dates[0], datetime) else dates[0]
    last_day = dates[-1].date() if isinstance(dates[-1], datetime) else dates[-1]
    print(f"Processing {len(dates)} days  ({first_day} → {last_day})")

    skipped = 0
    success = 0
    failed_records = []

    for item in tqdm(dates, desc="Days", unit="day"):
        if isinstance(item, pd.Timestamp):
            date = item.to_pydatetime()
        elif isinstance(item, datetime):
            date = item
        else:
            date = pd.to_datetime(item).to_pydatetime()
        out_file = output_dir / f"IMERG_V07_{region_name}_{date.strftime('%Y%m%d')}.nc"

        try:
            if out_file.exists():
                if is_valid_output_file(out_file):
                    skipped += 1
                    continue
                else:
                    try:
                        out_file.unlink()
                    except Exception:
                        pass

            day_staging = raw_dir / date.strftime("%Y%m%d")

            hdf5_files, download_error = download_day(date, day_staging)
            if not hdf5_files:
                failed_records.append(
                    {
                        "date": str(date.date()),
                        "stage": "download",
                        "message": download_error or "Unknown download error",
                    }
                )
                continue

            ok, build_error = build_daily_netcdf(
                date,
                hdf5_files,
                out_file,
                domain,
                region_name,
                compress_output=compress_output,
                compression_level=compression_level,
            )

            if ok:
                success += 1
                if not keep_raw:
                    for f in hdf5_files:
                        f.unlink(missing_ok=True)
                    try:
                        day_staging.rmdir()
                    except OSError:
                        pass
            else:
                failed_records.append(
                    {
                        "date": str(date.date()),
                        "stage": "build",
                        "message": build_error or "Unknown build error",
                    }
                )

        except Exception as exc:
            failed_records.append(
                {
                    "date": str(date.date()),
                    "stage": "unexpected",
                    "message": str(exc),
                }
            )
            continue

    print(f"\n── Summary ──────────────────────────────────────────────────")
    print(f"  Processed:  {success}")
    print(f"  Skipped:    {skipped}  (already existed)")
    print(f"  Failed:     {len(failed_records)}")
    if failed_records:
        failed_dates = [record["date"] for record in failed_records]
        print(f"  Failed dates: {failed_dates}")

    if failed_log_file is not None and failed_records:
        failed_log_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(failed_records).to_csv(failed_log_file, index=False)
        print(f"  Failure log: {failed_log_file}")

    print(f"  Output dir: {output_dir}")
    print(f"────────────────────────────────────────────────────────────\n")


def process_all(start: datetime, end: datetime,
                raw_dir: Path, output_dir: Path,
                domain: dict, region_name: str,
                keep_raw: bool,
                failed_log_file: Path | None = None,
                compress_output: bool = ENABLE_NETCDF_COMPRESSION,
                compression_level: int = NETCDF_COMPLEVEL) -> None:
    dates = pd.date_range(start, end, freq="D")
    process_dates(
        dates=dates,
        raw_dir=raw_dir,
        output_dir=output_dir,
        domain=domain,
        region_name=region_name,
        keep_raw=keep_raw,
        failed_log_file=failed_log_file,
        compress_output=compress_output,
        compression_level=compression_level,
    )


def load_failed_dates(csv_path: Path):
    """Load unique dates from failed-date CSV (expects column named 'date')."""
    if not csv_path.exists():
        sys.exit(f"ERROR: Failed-date CSV not found: {csv_path}")

    failed_df = pd.read_csv(csv_path)
    if "date" not in failed_df.columns:
        sys.exit(f"ERROR: CSV {csv_path} must contain a 'date' column")

    failed_dates = pd.to_datetime(failed_df["date"], errors="coerce").dropna().dt.date.unique()
    if len(failed_dates) == 0:
        print(f"No valid failed dates found in {csv_path}")
        return []

    return [datetime.combine(day, datetime.min.time()) for day in sorted(failed_dates)]


def parse_cli_args():
    """Optional CLI overrides for date range, domain, and directories."""
    parser = argparse.ArgumentParser(
        description="Download and preprocess IMERG for RainyDay-compatible daily NetCDF files."
    )
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--region-name", help="Region name used in output filename")
    parser.add_argument("--raw-dir", help="Raw HDF5 staging directory")
    parser.add_argument("--output-dir", help="Processed daily NetCDF output directory")

    parser.add_argument("--lat-min", type=float, help="Domain latitude minimum")
    parser.add_argument("--lat-max", type=float, help="Domain latitude maximum")
    parser.add_argument("--lon-min", type=float, help="Domain longitude minimum")
    parser.add_argument("--lon-max", type=float, help="Domain longitude maximum")

    parser.add_argument("--keep-raw", action="store_true", help="Keep raw downloaded HDF5 files")
    parser.add_argument("--no-compress", action="store_true", help="Disable NetCDF variable compression")
    parser.add_argument("--compression-level", type=int, default=NETCDF_COMPLEVEL,
                        help=f"NetCDF compression level (0-9), default={NETCDF_COMPLEVEL}")
    parser.add_argument("--failed-log", help="Path to CSV file for failed day diagnostics")
    parser.add_argument("--retry-failed-csv", help="Retry only dates listed in this failed_dates CSV")

    return parser.parse_args()


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    args = parse_cli_args()

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d") if args.start_date else START_DATE
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else END_DATE
    if end_date < start_date:
        sys.exit("ERROR: --end-date must be on or after --start-date")

    region_name = args.region_name if args.region_name else REGION_NAME
    raw_dir = Path(args.raw_dir) if args.raw_dir else RAW_DIR
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR

    domain = dict(DOMAIN)
    if args.lat_min is not None:
        domain["lat_min"] = args.lat_min
    if args.lat_max is not None:
        domain["lat_max"] = args.lat_max
    if args.lon_min is not None:
        domain["lon_min"] = args.lon_min
    if args.lon_max is not None:
        domain["lon_max"] = args.lon_max

    keep_raw = True if args.keep_raw else KEEP_RAW
    compress_output = False if args.no_compress else ENABLE_NETCDF_COMPRESSION
    compression_level = max(0, min(9, int(args.compression_level)))
    failed_log_file = Path(args.failed_log) if args.failed_log else (output_dir / "failed_dates.csv")

    retry_failed_csv = Path(args.retry_failed_csv) if args.retry_failed_csv else None

    if retry_failed_csv is None:
        print_storage_estimate(start_date, end_date, domain, keep_raw)

    authenticate()

    if retry_failed_csv is not None:
        retry_dates = load_failed_dates(retry_failed_csv)
        process_dates(
            dates=retry_dates,
            raw_dir=raw_dir,
            output_dir=output_dir,
            domain=domain,
            region_name=region_name,
            keep_raw=keep_raw,
            failed_log_file=failed_log_file,
            compress_output=compress_output,
            compression_level=compression_level,
        )
    else:
        process_all(
            start             = start_date,
            end               = end_date,
            raw_dir           = raw_dir,
            output_dir        = output_dir,
            domain            = domain,
            region_name       = region_name,
            keep_raw          = keep_raw,
            failed_log_file   = failed_log_file,
            compress_output   = compress_output,
            compression_level = compression_level,
        )

    # Verify the most recently created file
    nc_files = sorted(output_dir.glob(f"IMERG_V07_{region_name}_*.nc"))
    if nc_files:
        verify_file(nc_files[-1], domain)
        print(f"\nTotal files in output directory: {len(nc_files)}")
        print("\nRainyDay RAINPATH glob pattern:")
        print(f'  "RAINPATH": "{output_dir}/IMERG_V07_{region_name}_*.nc"')

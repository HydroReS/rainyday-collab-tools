"""
Convert RainyDay NetCDF outputs to individual time-slice GeoTIFF files.

What this script does
---------------------
- Accepts either:
    1) a single NetCDF file, or
    2) a root directory (e.g., output/.../Realizations) and recursively finds all .nc files.
- Exports one GeoTIFF per time step using the precipitation variable you specify.
- Supports two directory output layouts:
    - nested: preserve input subfolders and create one folder per .nc (default)
    - flat: write all .tif files into a single output folder

Typical usage
-------------
Single file mode:
    python scripts/convert_RainyDay_nc_to_tiff.py \
        output/Barbados_RainyDay/Barbados_IMERG_24h_fixed/Realizations/realization1/scenario_*.nc \
        geotiff_output --var rain

Directory mode (recommended for Realizations):
    python scripts/convert_RainyDay_nc_to_tiff.py \
        output/Barbados_RainyDay/Barbados_IMERG_24h_fixed/Realizations \
        geotiff_output --var rain

Directory mode with all TIFFs in one folder:
    python scripts/convert_RainyDay_nc_to_tiff.py \
        output/Barbados_RainyDay/Barbados_IMERG_24h_fixed/Realizations \
        geotiff_output --var rain --layout flat

Notes
-----
- Default variable is "rain"; if your files use another name, pass --var.
- CRS is written as EPSG:4326.
"""

import os
import argparse
import xarray as xr
import rioxarray as rio
import pandas as pd
from pathlib import Path

def convert_nc_to_tiffs(nc_filepath, output_dir, variable_name='rain', filename_prefix=''):
    """
    Converts a RainyDay NetCDF file into individual time-sliced GeoTIFFs.
    
    Args:
        nc_filepath (str): Path to the input .nc file.
        output_dir (str): Directory to save the output .tif files.
        variable_name (str): The name of the precipitation variable in the NetCDF.
                             (Common names: 'rain', 'precip', 'precipitation')
        filename_prefix (str): Optional prefix prepended to output TIFF names.
    """
    # Create the output directory if it doesn't exist
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract the base storm name from the file (e.g., 'scenario_Barbados_IMERG_24h_fixed_rlz1year1storm1')
    base_name = Path(nc_filepath).stem
    
    # Load the NetCDF file
    print(f"Loading {nc_filepath}...")
    ds = xr.open_dataset(nc_filepath)
    
    # Ensure the dataset has the correct spatial dimensions for rioxarray
    # RainyDay typically uses 'lon' and 'lat', but adjust if yours uses 'longitude'/'latitude'
    x_dim = 'lon' if 'lon' in ds.dims else 'longitude'
    y_dim = 'lat' if 'lat' in ds.dims else 'latitude'
    
    da = ds[variable_name]
    da = da.rio.set_spatial_dims(x_dim=x_dim, y_dim=y_dim)
    
    # Set the Coordinate Reference System (CRS) to WGS84 (EPSG:4326)
    # This is standard for IMERG data, but rioxarray needs it explicitly set to write a valid TIF
    da.rio.write_crs("epsg:4326", inplace=True)
    
    # Iterate through each time slice
    times = da['time'].values
    total_steps = len(times)
    
    print(f"Found {total_steps} time steps. Exporting to GeoTIFF...")
    
    for i, time_val in enumerate(times):
        # Extract the single time slice
        da_slice = da.isel(time=i)
        
        # Convert numpy datetime64 to a pandas Timestamp for easy formatting
        dt = pd.Timestamp(time_val)
        
        # Format: YYYYMMDDHHMM (matches EF5 requirements)
        dt_str = dt.strftime('%Y%m%d%H%M')
        
        # Create a filename that forces correct `ls` sorting:
        # e.g., scenario_Barbados_t001_201708251200.tif
        # The zero-padded index (i+1:04d) ensures t002 comes before t010 in Linux.
        filename = f"{filename_prefix}{base_name}_t{i+1:04d}_{dt_str}.tif"
        out_path = output_dir / filename
        
        # Write to GeoTIFF
        da_slice.rio.to_raster(out_path)
        print(f"Saved: {filename}")
        
    print(f"Successfully exported {total_steps} files to {output_dir}")
    ds.close()


def convert_realizations_tree(input_root, output_root, variable_name='rain', layout='nested'):
    """
    Recursively converts all NetCDF files under `input_root` to time-sliced GeoTIFFs.
    Output structure mirrors the input tree, and each NetCDF gets its own folder.

    Args:
        input_root (str | Path): Root directory containing Realizations subfolders.
        output_root (str | Path): Root directory where GeoTIFFs will be written.
        variable_name (str): Variable to export (default: 'rain').
        layout (str): Output layout for directory mode: 'nested' or 'flat'.
    """
    input_root = Path(input_root).resolve()
    output_root = Path(output_root).resolve()

    if not input_root.exists() or not input_root.is_dir():
        raise FileNotFoundError(f"Input root does not exist or is not a directory: {input_root}")

    nc_files = sorted(input_root.rglob("*.nc"))
    if not nc_files:
        raise FileNotFoundError(f"No .nc files found under: {input_root}")

    print(f"Found {len(nc_files)} NetCDF files under {input_root}")

    for idx, nc_file in enumerate(nc_files, start=1):
        rel_parent = nc_file.parent.relative_to(input_root)
        if layout == 'flat':
            per_file_output = output_root
            safe_prefix = f"{str(rel_parent).replace(os.sep, '_')}_" if str(rel_parent) != "." else ""
            filename_prefix = safe_prefix
        else:
            per_file_output = output_root / rel_parent / nc_file.stem
            filename_prefix = ""

        print(f"\n[{idx}/{len(nc_files)}] Converting: {nc_file}")
        print(f"Output folder: {per_file_output}")
        convert_nc_to_tiffs(nc_file, per_file_output, variable_name, filename_prefix)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert RainyDay NetCDF files to individual time-slice GeoTIFFs."
    )
    parser.add_argument(
        "input_path",
        help="Path to a single .nc file OR a root directory (e.g., output/Realizations).",
    )
    parser.add_argument(
        "output_path",
        help="Output directory where GeoTIFFs will be written.",
    )
    parser.add_argument(
        "--var",
        default="rain",
        help="Precipitation variable name in NetCDF (default: rain).",
    )
    parser.add_argument(
        "--layout",
        choices=["nested", "flat"],
        default="nested",
        help="Directory mode output layout: nested (default) or flat.",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    input_path = Path(args.input_path)

    if input_path.is_file():
        convert_nc_to_tiffs(input_path, args.output_path, args.var)
    elif input_path.is_dir():
        convert_realizations_tree(input_path, args.output_path, args.var, args.layout)
    else:
        raise FileNotFoundError(f"Input path does not exist: {input_path}")
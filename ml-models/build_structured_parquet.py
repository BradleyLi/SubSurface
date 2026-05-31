#!/usr/bin/env python3
"""
Build a structured parquet dataset for ML predicting watermain breaks.
Writes outputs to .structured-data/ (creates dir if missing):
 - panel.parquet  (rows: segment x year, ML-ready features + labels)
 - segments.geoparquet (segment-level geo dataframe)

Dependencies:
 pip install geopandas pandas pyarrow shapely fiona rtree

Usage:
 python build_structured_parquet.py

Notes:
 - Assumes source files are in .data/ in the same working directory as this script.
 - Buffer distance (meters) and panel year range are configurable.
"""

import os
import sys
from pathlib import Path
import warnings

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import numpy as np

# Configuration
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / ".data"
OUT_DIR = BASE / ".structured-data"
OUT_DIR.mkdir(exist_ok=True)

DIST_PATH = DATA_DIR / "distribution.geojson"
TRANS_PATH = DATA_DIR / "transmission.geojson"
TREE_PATH = DATA_DIR / "tree.geojson"
BREAKS_SHP = DATA_DIR / "watermain-break" / "Breaks_1990_2016_wgs84.shp"

# Parameters
BUFFER_M = 10  # meters for associating trees/breaks to segments
PANEL_YEARS = list(range(1990, 2017))  # inclusive 1990-2016 (breaks file span)
TREE_DBH_COL = "DBH_TRUNK"  # column in tree file

warnings.filterwarnings("ignore", category=UserWarning)


def read_watermains():
    d = gpd.read_file(DIST_PATH)
    d['source_layer'] = 'distribution'
    t = gpd.read_file(TRANS_PATH)
    t['source_layer'] = 'transmission'
    # unify columns by lowercasing keys
    gdf = pd.concat([d, t], ignore_index=True, sort=False)
    gdf = gpd.GeoDataFrame(gdf, geometry='geometry', crs=d.crs)

    # Normalize common property names
    prop_map = {
        'Watermain Asset Identification': 'asset_id',
        'Watermain Diameter': 'diameter_mm',
        'Watermain Material': 'material',
        'Watermain Construction Year': 'construction_year',
        'Watermain Measured Length': 'measured_length_m',
        'Watermain Install Date': 'install_date',
        'Watermain Type': 'watermain_type',
        'Watermain Location Description': 'location_desc'
    }

    # Normalize 'Watermain Install Date' directly to prevent mixed-type pyarrow failures on both original and renamed columns
    if 'Watermain Install Date' in gdf.columns:
        gdf['Watermain Install Date'] = pd.to_datetime(gdf['Watermain Install Date'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')

    for src, dst in prop_map.items():
        if src in gdf.columns:
            gdf[dst] = gdf[src]

    # Fallback ids
    if 'asset_id' not in gdf.columns or gdf['asset_id'].isnull().all():
        gdf['asset_id'] = gdf.index.astype(str)

    # Ensure geometry and CRS
    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    gdf = gdf.to_crs(epsg=4326)

    # make sure numeric types
    gdf['diameter_mm'] = pd.to_numeric(gdf.get('diameter_mm'), errors='coerce')
    gdf['construction_year'] = pd.to_numeric(gdf.get('construction_year'), errors='coerce').astype('Int64')
    gdf['measured_length_m'] = pd.to_numeric(gdf.get('measured_length_m'), errors='coerce')

    # normalize install_date to string to prevent mixed-type pyarrow failures
    if 'install_date' in gdf.columns:
        gdf['install_date'] = pd.to_datetime(gdf['install_date'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')
    else:
        gdf['install_date'] = ''

    # compute length in meters using projected CRS if missing or for normalization
    gdf_proj = gdf.to_crs(epsg=3857)
    gdf['computed_length_m'] = gdf_proj.geometry.length
    # prefer measured_length_m if present else computed
    gdf['length_m'] = gdf['measured_length_m'].fillna(gdf['computed_length_m'])

    # centroid lon/lat
    gdf['centroid_lon'] = gdf.geometry.centroid.x
    gdf['centroid_lat'] = gdf.geometry.centroid.y

    # canonical id
    gdf['segment_id'] = gdf['asset_id'].astype(str) + '::' + gdf.index.astype(str)

    return gdf


def read_trees():
    tg = gpd.read_file(TREE_PATH)
    if tg.crs is None:
        tg.set_crs(epsg=4326, inplace=True)
    tg = tg.to_crs(epsg=4326)
    # normalize dbh
    if TREE_DBH_COL in tg.columns:
        tg['dbh_cm'] = pd.to_numeric(tg[TREE_DBH_COL], errors='coerce')
    else:
        tg['dbh_cm'] = pd.NA
    return tg


def read_breaks():
    if not BREAKS_SHP.exists():
        raise FileNotFoundError(f"Breaks shapefile not found at {BREAKS_SHP}")
    bg = gpd.read_file(BREAKS_SHP)
    # expected fields: BREAK_DATE, BREAK_YEAR
    bg_cols = [c.upper() for c in bg.columns]
    # normalize
    if 'BREAK_YEAR' in bg.columns:
        bg['break_year'] = pd.to_numeric(bg['BREAK_YEAR'], errors='coerce').astype('Int64')
    elif 'BREAK_DATE' in bg.columns or 'BREAK_DATE' in bg_cols:
        # try parsing date field
        if 'BREAK_DATE' in bg.columns:
            bg['break_date'] = pd.to_datetime(bg['BREAK_DATE'], errors='coerce')
        else:
            # find something like break_date ignoring case
            for c in bg.columns:
                if c.upper() == 'BREAK_DATE':
                    bg['break_date'] = pd.to_datetime(bg[c], errors='coerce')
                    break
        bg['break_year'] = bg['break_date'].dt.year.astype('Int64')
    else:
        # try POINT_X/POINT_Y
        bg['break_year'] = pd.NA

    if bg.crs is None:
        bg.set_crs(epsg=4326, inplace=True)
    bg = bg.to_crs(epsg=4326)
    return bg


def aggregate_trees_to_segments(segments, trees, buffer_m=10):
    # project both to metric CRS for buffering/distance
    seg_p = segments.to_crs(epsg=3857).copy()
    tree_p = trees.to_crs(epsg=3857).copy()

    seg_p['buffer_geom'] = seg_p.geometry.buffer(buffer_m)
    buf_gdf = seg_p[['segment_id', 'buffer_geom', 'length_m']].copy()
    buf_gdf = gpd.GeoDataFrame(buf_gdf, geometry='buffer_geom', crs=seg_p.crs)
    buf_gdf = buf_gdf.rename(columns={'buffer_geom': 'geometry'}).set_geometry('geometry')

    # spatial join
    join = gpd.sjoin(tree_p, buf_gdf, how='inner', predicate='within')

    if join.empty:
        # return zeros
        agg = pd.DataFrame({
            'segment_id': segments['segment_id'],
            'trees_count': 0,
            'trees_with_dbh_count': 0,
            'avg_dbh_cm': np.nan,
            'median_dbh_cm': np.nan,
            'max_dbh_cm': np.nan,
            'sum_dbh_cm': 0,
            'trees_small_count': 0,
            'trees_medium_count': 0,
            'trees_large_count': 0,
            'trees_count_per_100m': 0.0
        })
        return agg.set_index('segment_id')

    # compute per segment aggregates
    join['dbh_cm'] = pd.to_numeric(join.get('dbh_cm'), errors='coerce')
    grp = join.groupby('segment_id')
    agg = grp.agg(
        trees_count=('geometry', 'count'),
        trees_with_dbh_count=('dbh_cm', lambda x: x.notna().sum()),
        avg_dbh_cm=('dbh_cm', 'mean'),
        median_dbh_cm=('dbh_cm', 'median'),
        max_dbh_cm=('dbh_cm', 'max'),
        sum_dbh_cm=('dbh_cm', 'sum')
    )
    # size buckets
    join['small'] = (join['dbh_cm'] < 10).fillna(False)
    join['medium'] = ((join['dbh_cm'] >= 10) & (join['dbh_cm'] < 30)).fillna(False)
    join['large'] = (join['dbh_cm'] >= 30).fillna(False)
    size = join.groupby('segment_id').agg(
        trees_small_count=('small', 'sum'),
        trees_medium_count=('medium', 'sum'),
        trees_large_count=('large', 'sum')
    )
    agg = agg.join(size)

    # normalize by length (per 100m)
    seg_lengths = segments.set_index('segment_id')['length_m']
    agg = agg.join(seg_lengths)
    agg['trees_count_per_100m'] = agg['trees_count'] / (agg['length_m'].replace(0, np.nan) / 100.0)
    agg['trees_count_per_100m'] = agg['trees_count_per_100m'].fillna(0.0)

    # ensure all segments present
    all_idx = pd.Index(segments['segment_id'])
    agg = agg.reindex(all_idx, fill_value=0)
    agg = agg.drop(columns=['length_m'], errors='ignore')

    return agg


def aggregate_breaks_to_segments(segments, breaks, buffer_m=10):
    seg_p = segments.to_crs(epsg=3857).copy()
    breaks_p = breaks.to_crs(epsg=3857).copy()

    seg_p['buffer_geom'] = seg_p.geometry.buffer(buffer_m)
    buf_gdf = seg_p[['segment_id', 'buffer_geom']].copy()
    buf_gdf = gpd.GeoDataFrame(buf_gdf, geometry='buffer_geom', crs=seg_p.crs)
    buf_gdf = buf_gdf.rename(columns={'buffer_geom': 'geometry'}).set_geometry('geometry')

    join = gpd.sjoin(breaks_p, buf_gdf, how='inner', predicate='within')

    if join.empty:
        return pd.DataFrame(columns=['segment_id', 'break_year', 'count']).set_index('segment_id')

    # get break_year column
    if 'break_year' not in join.columns:
        # try uppercase
        possible = [c for c in join.columns if c.upper().startswith('BREAK')]
        join['break_year'] = pd.to_numeric(join.get('BREAK_YEAR') if 'BREAK_YEAR' in join.columns else None, errors='coerce')

    join['break_year'] = pd.to_numeric(join['break_year'], errors='coerce').astype('Int64')
    # drop NA years
    join = join[join['break_year'].notna()]
    join['break_year'] = join['break_year'].astype(int)

    grp = join.groupby(['segment_id', 'break_year']).size().reset_index(name='count')
    # pivot to get counts per segment-year
    return grp


def build_panel(segments_df, trees_agg, breaks_grp, years=PANEL_YEARS):
    """Vectorized build of the panel (segment x year).

    Returns a pandas DataFrame with segment attributes, tree aggregates,
    break-history features and labels. This avoids Python-level loops for speed.
    """
    # keep selected segment attributes
    segs = segments_df[['segment_id', 'asset_id', 'diameter_mm', 'material', 'construction_year', 'install_date', 'length_m', 'centroid_lon', 'centroid_lat', 'source_layer']].copy()
    segs = segs.set_index('segment_id')

    # product of segments x years using MultiIndex (memory efficient)
    seg_ids = segs.index.unique()
    all_idx = pd.MultiIndex.from_product([seg_ids, years], names=['segment_id', 'year'])
    panel = pd.DataFrame(index=all_idx).reset_index()

    # merge static segment attributes (vectorized)
    panel = panel.merge(segs.reset_index(), on='segment_id', how='left')

    # merge tree aggregates (trees_agg may be a DataFrame indexed by segment_id)
    if isinstance(trees_agg, pd.DataFrame):
        trees_df = trees_agg.reset_index()
    else:
        trees_df = pd.DataFrame(trees_agg).reset_index()
    # ensure index name
    if 'segment_id' not in trees_df.columns and trees_df.columns[0] != 'segment_id':
        trees_df = trees_df.rename(columns={trees_df.columns[0]: 'segment_id'})

    panel = panel.merge(trees_df, on='segment_id', how='left')

    # fill tree aggregate missing values sensibly
    tree_defaults = {
        'trees_count': 0,
        'trees_with_dbh_count': 0,
        'avg_dbh_cm': np.nan,
        'median_dbh_cm': np.nan,
        'max_dbh_cm': np.nan,
        'sum_dbh_cm': 0,
        'trees_small_count': 0,
        'trees_medium_count': 0,
        'trees_large_count': 0,
        'trees_count_per_100m': 0.0
    }
    for k, v in tree_defaults.items():
        if k not in panel.columns:
            panel[k] = v
    panel[list(tree_defaults.keys())] = panel[list(tree_defaults.keys())].fillna(value=0)
    # restore NA for aggregate stats where appropriate
    panel['avg_dbh_cm'] = panel['avg_dbh_cm'].replace({0: np.nan})
    panel['median_dbh_cm'] = panel['median_dbh_cm'].replace({0: np.nan})
    panel['max_dbh_cm'] = panel['max_dbh_cm'].replace({0: np.nan})

    # prepare break counts per (segment_id, year)
    if breaks_grp is None or len(breaks_grp) == 0:
        # no breaks -> zero counts
        panel['break_count'] = 0
    else:
        # breaks_grp expected columns: segment_id, break_year, count
        bg = breaks_grp.copy()
        # normalize column names to known order
        bg = bg.rename(columns={bg.columns[0]: 'segment_id', bg.columns[1]: 'break_year', bg.columns[2]: 'count'})
        bg = bg[['segment_id', 'break_year', 'count']]
        # pivot via reindexing MultiIndex
        bc = bg.set_index(['segment_id', 'break_year'])['count']
        # reindex to full grid
        bc = bc.reindex(all_idx, fill_value=0).rename('break_count').reset_index()
        panel = panel.merge(bc, on=['segment_id', 'year'], how='left')
        panel['break_count'] = panel['break_count'].fillna(0).astype('int16')

    # sort for groupby operations
    panel = panel.sort_values(['segment_id', 'year']).reset_index(drop=True)

    # label: breaks next year (shifted -1)
    panel['breaks_count_next_year'] = panel.groupby('segment_id')['break_count'].shift(-1).fillna(0).astype('int16')
    panel['break_next_year'] = (panel['breaks_count_next_year'] > 0).astype('int8')

    # rolling historical counts (including current year)
    # breaks_past_1yr == current year, breaks_past_3yr == current + previous 2, etc.
    panel['breaks_past_1yr'] = panel.groupby('segment_id')['break_count'].rolling(window=1, min_periods=1).sum().reset_index(level=0, drop=True).astype('int16')
    panel['breaks_past_3yr'] = panel.groupby('segment_id')['break_count'].rolling(window=3, min_periods=1).sum().reset_index(level=0, drop=True).astype('int16')
    panel['breaks_past_5yr'] = panel.groupby('segment_id')['break_count'].rolling(window=5, min_periods=1).sum().reset_index(level=0, drop=True).astype('int16')

    # years since last break
    panel['last_break_year'] = panel['year'].where(panel['break_count'] > 0)
    panel['last_break_year'] = panel.groupby('segment_id')['last_break_year'].ffill()
    panel['years_since_last_break'] = (panel['year'] - panel['last_break_year']).where(panel['last_break_year'].notna())
    panel['years_since_last_break'] = panel['years_since_last_break'].astype('Int64')

    # age and derived features
    panel['age_years'] = panel['year'] - pd.to_numeric(panel['construction_year'], errors='coerce')
    panel['age_years'] = panel['age_years'].astype('Int64')

    panel['log_length'] = np.log1p(pd.to_numeric(panel['length_m'], errors='coerce').fillna(0.0))
    panel['age_x_diameter'] = (pd.to_numeric(panel['age_years'], errors='coerce').fillna(0.0) *
                               pd.to_numeric(panel['diameter_mm'], errors='coerce').fillna(0.0))

    # tidy types
    panel['year'] = panel['year'].astype('int16')
    panel['break_next_year'] = panel['break_next_year'].astype('int8')

    # drop helper column
    panel = panel.drop(columns=['last_break_year'], errors='ignore')

    return panel


def main():
    print('\nReading source layers...')
    segments = read_watermains()
    print(f'  segments: {len(segments)}')
    trees = read_trees()
    print(f'  trees: {len(trees)}')
    breaks = read_breaks()
    print(f'  breaks: {len(breaks)}')

    print('\nAggregating trees to segments (buffer: {} m)...'.format(BUFFER_M))
    trees_agg = aggregate_trees_to_segments(segments, trees, buffer_m=BUFFER_M)
    print('  tree-aggregates computed')

    print('\nAggregating breaks to segments...')
    breaks_grp = aggregate_breaks_to_segments(segments, breaks, buffer_m=BUFFER_M)
    print('  break-aggregates computed')

    print('\nBuilding panel (years {}..{})...'.format(min(PANEL_YEARS), max(PANEL_YEARS)))
    panel = build_panel(segments, trees_agg, breaks_grp, years=PANEL_YEARS)
    print('  panel rows:', len(panel))

    # Save outputs
    panel_path = OUT_DIR / 'panel.parquet'
    segments_path = OUT_DIR / 'segments.geoparquet'

    def write_parquet_only(df, path):
        """Write dataframe to parquet using pyarrow or fastparquet. Raise if none available.

        This script enforces parquet-only outputs per user request.
        """
        try:
            import pyarrow  # noqa: F401
            engine = 'pyarrow'
        except Exception:
            try:
                import fastparquet  # noqa: F401
                engine = 'fastparquet'
            except Exception:
                raise RuntimeError('\nNo parquet engine found. Please install pyarrow (recommended):\n  pip install pyarrow\nOr install fastparquet:\n  pip install fastparquet\n')

        # Ensure parent dir exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False, engine=engine)

    print('\nWriting parquet to {}...'.format(panel_path))
    write_parquet_only(panel, panel_path)
    print('Writing segments geoparquet to {}...'.format(segments_path))
    write_parquet_only(segments, segments_path)

    print('\nDone. Outputs in', OUT_DIR)


if __name__ == '__main__':
    main()

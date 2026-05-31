#!/usr/bin/env python3
"""
Train a GPU XGBoost model using XGBClassifier API with CUDA, cuDF inputs, and SHAP.
This version aligns with the provided training pattern but improves safety, early stopping,
categorical handling, missing-value indicators, and explicit GPU params.

Requirements (GPU-enabled environment):
  - RAPIDS cuDF
  - xgboost with GPU support (pip/conda wheel compatible with CUDA)
  - shap
  - scikit-learn

Usage:
  python train_xgb_gpu.py

Outputs in .structured-data/models:
  - xgb_model.json
  - feature_importance.csv
  - shap_feature_importance.csv
  - metrics.json

"""

import sys
from pathlib import Path
import json
import argparse
import warnings
import logging

# Helpful imports with clear errors
try:
    import cudf
    import cupy as cp
except Exception:
    raise RuntimeError("cudf and cupy are required. Install RAPIDS/cuDF and cupy in a CUDA-enabled environment.")

try:
    import xgboost as xgb
    from xgboost import XGBClassifier
except Exception:
    raise RuntimeError("xgboost with CUDA support is required. Install a GPU-enabled xgboost build.")

try:
    import shap
except Exception:
    raise RuntimeError("shap is required: pip install shap")

import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score, f1_score, classification_report

# Paths
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / '.structured-data'
PANEL_PQ = DATA_DIR / 'panel.parquet'
MODELS_DIR = DATA_DIR / 'models'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def log_gpu_info(gpu_id=0):
    """Log GPU and library information to verify GPU usage."""
    try:
        # cupy device count and properties
        dev_count = cp.cuda.runtime.getDeviceCount()
        props = cp.cuda.runtime.getDeviceProperties(gpu_id)
        # props may be tuple-like, try to get name field
        try:
            dev_name = props['name'] if isinstance(props, dict) and 'name' in props else getattr(props, 'name', str(props))
        except Exception:
            dev_name = str(props)
        logger.info(f"CuPy device count: {dev_count}; using GPU id: {gpu_id}; device name: {dev_name}")
    except Exception as e:
        logger.warning(f"Unable to query CuPy device info: {e}")

    try:
        logger.info(f"cuDF version: {cudf.__version__}")
    except Exception:
        logger.warning("cuDF version not available")
    try:
        logger.info(f"XGBoost version: {xgb.__version__}")
    except Exception:
        logger.warning("XGBoost version not available")
    try:
        import shap
        logger.info(f"SHAP version: {shap.__version__}")
    except Exception:
        logger.warning("SHAP version not available")


# CLI
parser = argparse.ArgumentParser()
parser.add_argument('--panel', default=str(PANEL_PQ))
parser.add_argument('--target', default='break_next_year')
parser.add_argument('--snapshot-col', default='year', help='column representing snapshot year')
parser.add_argument('--id-col', default='segment_id')
parser.add_argument('--gpu-id', type=int, default=0)
parser.add_argument('--n-estimators', type=int, default=2000)
parser.add_argument('--learning-rate', type=float, default=0.03)
parser.add_argument('--max-depth', type=int, default=8)
parser.add_argument('--subsample', type=float, default=0.8)
parser.add_argument('--colsample', type=float, default=0.8)
parser.add_argument('--min-child-weight', type=float, default=5.0)
parser.add_argument('--gamma', type=float, default=1.0)
parser.add_argument('--reg-alpha', type=float, default=0.1)
parser.add_argument('--reg-lambda', type=float, default=1.0)
parser.add_argument('--train-end-year', type=int, default=None, help='last year to include in train')
parser.add_argument('--val-start', type=int, default=None, help='start year for validation')
parser.add_argument('--val-end', type=int, default=None, help='end year for validation')
parser.add_argument('--test-start', type=int, default=None, help='start year for test')
parser.add_argument('--threshold', type=float, default=0.5)
parser.add_argument('--sample-shap', type=int, default=5000)
args = parser.parse_args()

# Load data
panel_path = Path(args.panel)
if not panel_path.exists():
    raise SystemExit(f'Panel file not found: {panel_path} — run build_structured_parquet.py first')

logger.info('Loading panel into cuDF...')
df = cudf.read_parquet(str(panel_path))
logger.info('Rows: %d', len(df))
# Log GPU and library versions
log_gpu_info(gpu_id=args.gpu_id)

# Column names
TARGET = args.target
YEAR_COL = args.snapshot_col
ID_COL = args.id_col

if TARGET not in df.columns:
    raise SystemExit(f"Target column '{TARGET}' not found")
if YEAR_COL not in df.columns:
    raise SystemExit(f"Year/snapshot column '{YEAR_COL}' not found")

# Time splits — allow explicit years or defaults similar to sample
years = sorted(list(map(int, df[YEAR_COL].unique().to_arrow().to_pylist())))
print('Available years:', years[:3], '...', years[-3:])

if args.train_end_year is not None:
    train_years = [y for y in years if y <= args.train_end_year]
    val_years = [y for y in years if args.val_start is not None and args.val_end is not None and (y >= args.val_start and y <= args.val_end)]
    test_years = [y for y in years if args.test_start is not None and y >= args.test_start]
else:
    # default split like sample: train <= 2011, val 2012-2013, test >= 2014
    train_years = [y for y in years if y <= 2011]
    val_years = [y for y in years if 2012 <= y <= 2013]
    test_years = [y for y in years if y >= 2014]

logger.info('Train years: %s', ( (min(train_years), max(train_years)) if train_years else 'none' ))
logger.info('Val years: %s', val_years)
logger.info('Test years: %s', ( (min(test_years), max(test_years)) if test_years else 'none' ))

train_df = df[df[YEAR_COL].isin(train_years)]
val_df = df[df[YEAR_COL].isin(val_years)]
test_df = df[df[YEAR_COL].isin(test_years)]
logger.info('Rows train/val/test: %d / %d / %d', len(train_df), len(val_df), len(test_df))

# FEATURES: drop id and target
DROP_COLS = [ID_COL, TARGET, YEAR_COL]
FEATURES = [c for c in df.columns if c not in DROP_COLS]
logger.info('Initial feature count: %d', len(FEATURES))

# Drop extremely high-cardinality string cols (heuristic)
keep_features = []
for c in FEATURES:
    if df[c].dtype == 'object' or str(df[c].dtype).startswith('str'):
        nuniq = int(df[c].nunique())
        if nuniq > 200:
            warnings.warn(f"Dropping high-cardinality string column: {c} (unique={nuniq})")
            continue
    keep_features.append(c)
FEATURES = keep_features
logger.info('Features after pruning: %d', len(FEATURES))

# Categorical encoding (small cats)
cat_cols = [c for c in FEATURES if df[c].dtype == 'object' or str(df[c].dtype).startswith('str')]
logger.info('Categorical columns: %s', cat_cols)
for c in cat_cols:
    df[c] = df[c].astype('category')
    # cuDF codes: -1 for nulls
    df[c] = df[c].cat.codes.astype('int32')

# Convert datetime-like columns to integer epoch (ms) because xgboost DMatrix from pandas
# rejects datetime64 dtypes unless enable_categorical is set. Handle in-place to avoid pandas fallback.
datetime_cols = [c for c in FEATURES if 'datetime' in str(df[c].dtype) or 'timestamp' in str(df[c].dtype)]
if datetime_cols:
    logger.info('Converting datetime columns to int64 epoch ms: %s', datetime_cols)
for c in datetime_cols:
    # add missing indicator
    miss = f'{c}__isnan'
    if df[c].isnull().any():
        df[miss] = df[c].isnull().astype('int8')
        FEATURES.append(miss)
    try:
        # cuDF supports astype('int64') for datetime to epoch
        df[c] = df[c].astype('int64')
    except Exception:
        # fallback: convert to pandas then to int64
        logger.info('Fallback converting datetime col %s via pandas', c)
        df[c] = df[c].to_pandas().astype('int64')
    # fill NaN (which become large negative if using pandas conversion). Replace NaN with 0
    try:
        df[c] = df[c].fillna(0)
    except Exception:
        pass

# Missing indicators and numeric fill
numeric_cols = [c for c in FEATURES if c not in cat_cols]
# add missing indicators for numeric columns
for c in numeric_cols:
    if df[c].isnull().any():
        miss = f'{c}__isnan'
        df[miss] = df[c].isnull().astype('int8')
        FEATURES.append(miss)

# compute median from training and fill
train_df = df[df[YEAR_COL].isin(train_years)]
medians = {}
for c in numeric_cols:
    med = train_df[c].median()
    med = 0 if med is None else med
    medians[c] = med
    df[c] = df[c].fillna(med)

# refresh splits
train_df = df[df[YEAR_COL].isin(train_years)]
val_df = df[df[YEAR_COL].isin(val_years)]
test_df = df[df[YEAR_COL].isin(test_years)]

# prepare X/y
X_train = train_df[FEATURES]
y_train = train_df[TARGET].astype('int8')
X_val = val_df[FEATURES]
y_val = val_df[TARGET].astype('int8')
X_test = test_df[FEATURES]
y_test = test_df[TARGET].astype('int8')

# scale_pos_weight
pos = int(y_train.sum())
neg = int(len(y_train) - pos)
scale_pos_weight = (neg / pos) if pos > 0 else 1.0
logger.info('scale_pos_weight = %s', scale_pos_weight)

# Convert to host pandas only if xgboost cannot accept cuDF directly
# Use xgboost.train (Booster) with DMatrix for compatibility and explicit GPU usage
logger.info('Converting datasets to DMatrix for xgboost.train')
try:
    dtrain = xgb.DMatrix(X_train, label=y_train)
    dval = xgb.DMatrix(X_val, label=y_val)
    dtest = xgb.DMatrix(X_test, label=y_test)
except Exception:
    logger.info('DMatrix from cuDF failed; converting to pandas')
    dtrain = xgb.DMatrix(X_train.to_pandas(), label=y_train.to_pandas())
    dval = xgb.DMatrix(X_val.to_pandas(), label=y_val.to_pandas())
    dtest = xgb.DMatrix(X_test.to_pandas(), label=y_test.to_pandas())

params = {
    'tree_method': 'hist',
    'predictor': 'gpu_predictor',
    'device': f'cuda',
    'objective': 'binary:logistic',
    'eval_metric': ['auc', 'aucpr', 'logloss'],
    'eta': args.learning_rate,
    'max_depth': args.max_depth,
    'subsample': args.subsample,
    'colsample_bytree': args.colsample,
    'min_child_weight': args.min_child_weight,
    'gamma': args.gamma,
    'reg_alpha': args.reg_alpha,
    'reg_lambda': args.reg_lambda,
    'scale_pos_weight': scale_pos_weight,
    'verbosity': 1
}

# GPU-only training: attempt GPU train and error if GPU not available / not supported
logger.info('Starting xgboost.train with GPU params (GPU-only mode)')
try:
    bst = xgb.train(
        params,
        dtrain,
        num_boost_round=args.n_estimators,
        evals=[(dtrain, 'train'), (dval, 'val')],
        early_stopping_rounds=50,
        verbose_eval=100
    )
    logger.info('Trained with GPU settings')
except Exception as e:
    # Provide actionable error for GPU setup
    msg = (
        'GPU training failed. This script requires a GPU-enabled XGBoost build and a CUDA-capable environment. '
        'Caught exception: {}\n'.format(e) +
        'Checklist:\n'
        ' - Is CUDA available and visible to this process? (nvidia-smi)\n'
        ' - Is xgboost built with GPU support? Install a GPU wheel or use conda (see https://xgboost.readthedocs.io/en/stable/gpu/index.html)\n'
        ' - Ensure RAPIDS/cuDF and cupy are installed and compatible with your CUDA version.\n'
        'XGBoost error details: {}'
    ).format(type(e).__name__, str(e))
    logger.error(msg)
    raise RuntimeError(msg)

logger.info('Best iteration: %s', getattr(bst, 'best_iteration', None))

# Predict on test DMatrix
logger.info('Predicting on test set using Booster')
probs = bst.predict(dtest)
probs_cpu = probs if isinstance(probs, np.ndarray) else np.array(probs)
try:
    y_test_cpu = y_test.to_pandas()
except Exception:
    y_test_cpu = y_test

preds_cpu = (probs_cpu > args.threshold).astype(int)

# metrics
roc_auc = roc_auc_score(y_test_cpu, probs_cpu)
pr_auc = average_precision_score(y_test_cpu, probs_cpu)
f1 = f1_score(y_test_cpu, preds_cpu)

metrics_out = {
    'roc_auc': float(roc_auc),
    'pr_auc': float(pr_auc),
    'f1': float(f1)
}
print('Metrics:', metrics_out)

# save model
model_path = MODELS_DIR / 'xgb_model.json'
bst.save_model(str(model_path))
print('Saved model to', model_path)

# SHAP
print('Computing SHAP...')
sample_size = min(args.sample_shap, len(X_test))
if sample_size > 0:
    X_shap = X_test.head(sample_size).to_pandas()
    explainer = shap.TreeExplainer(bst)
    shap_vals = explainer.shap_values(X_shap)
    mean_abs_shap = np.abs(shap_vals).mean(axis=0)
    shap_df = pd.DataFrame({'feature': FEATURES, 'mean_abs_shap': mean_abs_shap})
    shap_df = shap_df.sort_values('mean_abs_shap', ascending=False)
    shap_df.to_csv(MODELS_DIR / 'shap_feature_importance.csv', index=False)

# metrics file
with open(MODELS_DIR / 'metrics.json', 'w') as f:
    json.dump(metrics_out, f, indent=2)

print('Done. Artifacts in', MODELS_DIR)

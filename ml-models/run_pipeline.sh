#!/usr/bin/env bash
# ==============================================================================
# SubSurface ML Pipeline Orchestrator (run_pipeline.sh)
# Fuses, structures, trains, and scores watermain break models on GPU
# ==============================================================================

set -euo pipefail

# ANSI color codes for premium, polished console output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Script directory is the source of truth
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

ENV_NAME="rapids-26.04"

# Resolve environment file location (prioritize parent directory for rapids-26.04 specification)
if [ -f "../environment.yml" ]; then
    ENV_FILE="../environment.yml"
else
    ENV_FILE="environment.yml"
fi

log_info() {
    echo -e "${BLUE}${BOLD}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}${BOLD}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}${BOLD}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}${BOLD}[ERROR]${NC} $1"
}

header() {
    echo -e "\n${CYAN}${BOLD}======================================================================"
    echo -e "  $1"
    echo -e "======================================================================${NC}\n"
}

# 1. Locate Conda executable robustly, or download & install if missing
header "Step 1: Locating Conda Installation"
CONDA_EXE=""
if command -v conda &> /dev/null; then
    CONDA_EXE="conda"
else
    # Check common locations
    COMMON_CONDA_PATHS=(
        "$HOME/miniconda3/bin/conda"
        "$HOME/anaconda3/bin/conda"
        "/opt/conda/bin/conda"
        "$HOME/opt/anaconda3/bin/conda"
        "/usr/local/bin/conda"
        "/home/asus/miniconda3/bin/conda"
        "/home/asus/anaconda3/bin/conda"
    )
    for path in "${COMMON_CONDA_PATHS[@]}"; do
        if [ -x "$path" ]; then
            CONDA_EXE="$path"
            break
        fi
    done
fi

if [ -z "$CONDA_EXE" ]; then
    log_warn "Conda executable could not be found."
    INSTALLER="Miniconda3-latest-Linux-aarch64.sh"
    INSTALL_DIR="$HOME/miniconda3"
    
    # Check parent directory for existing installer to save download time
    if [ -f "../$INSTALLER" ] && [ ! -f "$INSTALLER" ]; then
        log_info "Found Miniconda installer in the parent directory. Copying locally..."
        cp "../$INSTALLER" .
    fi
    
    if [ ! -f "$INSTALLER" ]; then
        log_info "Downloading Miniconda installer from official repo..."
        curl -O "https://repo.anaconda.com/miniconda/$INSTALLER"
    else
        log_info "Using existing local installer: $INSTALLER"
    fi
    
    log_info "Installing Miniconda silently to $INSTALL_DIR..."
    bash "$INSTALLER" -b -p "$INSTALL_DIR" -u
    
    CONDA_EXE="$INSTALL_DIR/bin/conda"
    log_success "Miniconda successfully installed at: $CONDA_EXE"
else
    log_success "Conda detected: $CONDA_EXE ($( "$CONDA_EXE" --version ))"
fi

# 2. Check if the environment exists or create it
header "Step 2: Checking/Setting up Conda Environment"
if "$CONDA_EXE" info --envs | grep -q "^${ENV_NAME} "; then
    log_success "Conda environment '${ENV_NAME}' already exists."
    log_info "Using the existing environment. (To recreate: run 'conda env remove -n ${ENV_NAME}' first)"
else
    log_warn "Conda environment '${ENV_NAME}' not found. Creating it..."
    if [ ! -f "${ENV_FILE}" ]; then
        log_error "Environment file '${ENV_FILE}' not found."
        exit 1
    fi
    log_info "Creating env from ${ENV_FILE} (${ENV_NAME}). This might take a few minutes..."
    "$CONDA_EXE" env create -f "${ENV_FILE}" -n "${ENV_NAME}"
    log_success "Conda environment '${ENV_NAME}' created successfully."
fi

# Helper function to run script with exact execution logs and performance metrics
run_in_env() {
    local script="$1"
    local desc="$2"
    
    log_info "Starting ${desc}..."
    local start_time=$(date +%s)
    
    # Execute the python script via conda run
    if "$CONDA_EXE" run --no-capture-output -n "${ENV_NAME}" python ${script}; then
        local end_time=$(date +%s)
        local elapsed=$((end_time - start_time))
        log_success "${desc} completed successfully in ${elapsed}s."
    else
        log_error "Execution failed during: ${desc}"
        exit 1
    fi
}

# 3. Download data
header "Step 3: Downloading Watermain and stressor datasets"
run_in_env "download_data.py" "Data Download Script (download_data.py)"

# 4. Build structured Parquet
header "Step 4: Geospatial fusion & feature engineering"
run_in_env "build_structured_parquet.py" "Feature Structuring Script (build_structured_parquet.py)"

# 5. Train GPU XGBoost Model
header "Step 5: Training XGBoost classifier on GPU"
run_in_env "train_xgb_gpu.py" "GPU Model Training (train_xgb_gpu.py)"

# 6. Run GPU Predictions
header "Step 6: Executing Pipeline Model Inference"
run_in_env "predict_xgb_gpu.py --start-year 2015 --end-year 2016" "GPU Scoring & SHAP generation (predict_xgb_gpu.py)"

header "SubSurface ML Pipeline Executed Successfully!"
log_success "All stages finished. Models, metrics, and scoring outputs are saved."
log_info "Pipeline products are located in: ${SCRIPT_DIR}/.structured-data/"

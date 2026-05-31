#!/usr/bin/env python3
"""
SubSurface ML Pipeline Orchestrator (run_pipeline.py)
Unified pipeline manager to handle:
  1. Conda Environment Setup (Installs Miniconda if missing, targets rapids-26.04)
  2. Data Download (download_data.py)
  3. Geospatial Feature Engineering (build_structured_parquet.py)
  4. GPU Model Training (train_xgb_gpu.py)
  5. GPU Model Inference & SHAP scoring (predict_xgb_gpu.py)
"""

import os
import sys
import argparse
import subprocess
import time
from pathlib import Path
import shutil

# Fancy terminal styling helpers
class Styles:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def log_info(msg: str):
    print(f"{Styles.BLUE}{Styles.BOLD}[INFO]{Styles.ENDC} {msg}")

def log_success(msg: str):
    print(f"{Styles.GREEN}{Styles.BOLD}[SUCCESS]{Styles.ENDC} {msg}")

def log_warn(msg: str):
    print(f"{Styles.WARNING}{Styles.BOLD}[WARNING]{Styles.ENDC} {msg}")

def log_error(msg: str):
    print(f"{Styles.FAIL}{Styles.BOLD}[ERROR]{Styles.ENDC} {msg}")

def log_header(title: str):
    width = 72
    print(f"\n{Styles.CYAN}{Styles.BOLD}" + "=" * width)
    print(f"  {title.center(width - 4)}")
    print("=" * width + f"{Styles.ENDC}\n")

# Source of truth
BASE_DIR = Path(__file__).resolve().parent
ENV_NAME = "rapids-26.04"

# Prioritize parent directory's environment file (defining rapids-26.04)
if (BASE_DIR.parent / "environment.yml").is_file():
    ENV_FILE = BASE_DIR.parent / "environment.yml"
else:
    ENV_FILE = BASE_DIR / "environment.yml"

def find_or_install_conda() -> str:
    """Robustly locate the conda or mamba executable, or download and install it if missing."""
    # Check if in PATH
    conda_path = shutil.which("conda")
    if conda_path:
        return conda_path

    # Check common locations
    home = Path.home()
    common_paths = [
        home / "miniconda3/bin/conda",
        home / "anaconda3/bin/conda",
        Path("/opt/conda/bin/conda"),
        home / "opt/anaconda3/bin/conda",
        Path("/usr/local/bin/conda"),
        Path("/home/asus/miniconda3/bin/conda"),
        Path("/home/asus/anaconda3/bin/conda"),
    ]
    for path in common_paths:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    # Conda is missing. Auto-download and install Miniconda!
    log_warn("Conda executable could not be found. Automatically preparing Miniconda installation...")
    installer_name = "Miniconda3-latest-Linux-aarch64.sh"
    installer_url = f"https://repo.anaconda.com/miniconda/{installer_name}"
    local_installer = BASE_DIR / installer_name
    parent_installer = BASE_DIR.parent / installer_name
    install_dir = home / "miniconda3"
    
    # Optimize by checking if it exists in the parent workspace dir
    if parent_installer.is_file() and not local_installer.is_file():
        log_info(f"Found Miniconda installer in the parent directory. Copying to {local_installer}...")
        try:
            shutil.copy(parent_installer, local_installer)
        except Exception as e:
            log_warn(f"Failed to copy parent installer: {e}. Downloading instead.")
            
    if not local_installer.is_file():
        log_info(f"Downloading Miniconda installer from official repository...")
        try:
            subprocess.run(["curl", "-O", installer_url], check=True, cwd=str(BASE_DIR))
        except Exception as e:
            log_error(f"Failed to download Miniconda: {e}")
            sys.exit(1)
            
    log_info(f"Installing Miniconda silently to: {install_dir}...")
    try:
        subprocess.run(["bash", str(local_installer), "-b", "-p", str(install_dir), "-u"], check=True)
    except Exception as e:
        log_error(f"Installation failed: {e}")
        sys.exit(1)
        
    conda_exe = install_dir / "bin" / "conda"
    if conda_exe.is_file() and os.access(conda_exe, os.X_OK):
        log_success(f"Miniconda successfully installed at: {conda_exe}")
        return str(conda_exe)
    else:
        log_error("Could not find the installed conda executable after running the script.")
        sys.exit(1)

def run_command(cmd: list[str], description: str) -> float:
    """Run a command with real-time streaming output and track duration."""
    log_info(f"Starting: {description}...")
    start_time = time.time()
    
    try:
        # Standard subprocess run that forwards stdout and stderr directly to user terminal
        process = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            cwd=str(BASE_DIR)
        )
        rc = process.wait()
        
        duration = time.time() - start_time
        if rc != 0:
            log_error(f"Process returned non-zero exit code: {rc}")
            sys.exit(rc)
            
        log_success(f"{description} completed successfully in {duration:.2f} seconds.")
        return duration
    except KeyboardInterrupt:
        log_error("\nPipeline interrupted by user.")
        sys.exit(1)
    except Exception as e:
        log_error(f"Exception raised while running command: {e}")
        sys.exit(1)

def check_env(conda_exe: str) -> bool:
    """Check if the subsurface conda environment exists."""
    try:
        out = subprocess.check_output([conda_exe, "info", "--envs"], text=True)
        return any(line.split()[0] == ENV_NAME for line in out.splitlines() if line and not line.startswith("#"))
    except Exception as e:
        log_warn(f"Could not list conda environments: {e}")
        return False

def setup_env(conda_exe: str, recreate: bool = False):
    """Sets up the conda environment from environment.yml."""
    log_header("Conda Environment Setup")
    env_exists = check_env(conda_exe)
    
    if env_exists and not recreate:
        log_success(f"Conda environment '{ENV_NAME}' already exists.")
        log_info("To recreate it, run this script with the --recreate-env flag.")
        return
        
    if env_exists and recreate:
        log_warn(f"Recreating existing conda environment '{ENV_NAME}'...")
        run_command([conda_exe, "env", "remove", "-y", "-n", ENV_NAME], "Removing existing conda env")
        
    log_info(f"Creating environment '{ENV_NAME}' from file: {ENV_FILE}")
    if not ENV_FILE.exists():
        log_error(f"Environment specification not found at: {ENV_FILE}")
        sys.exit(1)
        
    run_command([conda_exe, "env", "create", "-f", str(ENV_FILE), "-n", ENV_NAME], "Conda env creation")
    log_success(f"Conda environment '{ENV_NAME}' successfully prepared.")

def main():
    parser = argparse.ArgumentParser(description="SubSurface ML Pipeline Orchestrator")
    parser.add_argument("--setup-only", action="store_true", help="Only verify/set up the conda environment")
    parser.add_argument("--skip-setup", action="store_true", help="Skip checking/setting up the conda environment")
    parser.add_argument("--recreate-env", action="store_true", help="Force remove and recreate the conda environment")
    parser.add_argument("--start-year", type=int, default=2015, help="Start year for scoring (predict_xgb_gpu.py)")
    parser.add_argument("--end-year", type=int, default=2016, help="End year for scoring (predict_xgb_gpu.py)")
    parser.add_argument("--gpu-id", type=int, default=0, help="CUDA GPU device ID for training")
    parser.add_argument("--skip-shap", action="store_true", help="Skip SHAP explainability calculations during scoring")
    parser.add_argument("--step", choices=["download", "build", "train", "predict"], help="Run only a single specific step of the pipeline")
    
    args = parser.parse_args()
    
    log_header("SubSurface ML Pipeline")
    conda_exe = find_or_install_conda()
    
    if not args.skip_setup:
        setup_env(conda_exe, recreate=args.recreate_env)
        
    if args.setup_only:
        log_info("Setup only requested. Exiting pipeline.")
        return
        
    # Build steps mapping
    steps = []
    
    # 1. Download
    if not args.step or args.step == "download":
        steps.append({
            "name": "download",
            "cmd": [conda_exe, "run", "--no-capture-output", "-n", ENV_NAME, "python", "download_data.py"],
            "desc": "Downloading watermain & tree datasets"
        })
        
    # 2. Build Structured
    if not args.step or args.step == "build":
        steps.append({
            "name": "build",
            "cmd": [conda_exe, "run", "--no-capture-output", "-n", ENV_NAME, "python", "build_structured_parquet.py"],
            "desc": "Geospatial fusion & structuring parquet"
        })
        
    # 3. Train XGB
    if not args.step or args.step == "train":
        steps.append({
            "name": "train",
            "cmd": [conda_exe, "run", "--no-capture-output", "-n", ENV_NAME, "python", "train_xgb_gpu.py", "--gpu-id", str(args.gpu_id)],
            "desc": "GPU XGBoost model training"
        })
        
    # 4. Predict
    if not args.step or args.step == "predict":
        pred_cmd = [
            conda_exe, "run", "--no-capture-output", "-n", ENV_NAME, "python", "predict_xgb_gpu.py",
            "--start-year", str(args.start_year),
            "--end-year", str(args.end_year)
        ]
        if args.skip_shap:
            pred_cmd.append("--skip-shap")
            
        steps.append({
            "name": "predict",
            "cmd": pred_cmd,
            "desc": f"GPU Inference & Scoring (Years: {args.start_year} - {args.end_year})"
        })

    # Execute selected steps
    durations = {}
    for step in steps:
        log_header(f"Pipeline Stage: {step['desc']}")
        duration = run_command(step["cmd"], step["desc"])
        durations[step["name"]] = duration
        
    # Print execution summary
    log_header("Pipeline Execution Summary")
    total_time = sum(durations.values())
    for name, dur in durations.items():
        print(f"  - {name.capitalize():<12}: {dur:6.2f} seconds ({dur/total_time*100:4.1f}%)")
    print("-" * 72)
    print(f"  Total Pipeline Time: {total_time:.2f} seconds\n")
    log_success("All requested pipeline steps completed successfully!")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_ddec6_batch.py - Batch preparation of DDEC6 charge calculations (supports recursive search of subfolders)
Usage:
    ./run_ddec6_batch.py [Atomic Density Index] [--submit]
Eg:
    ./run_ddec6_batch.py /home/naturegogo/bin/atomic_densities/ --submit
"""

import os
import sys
import argparse
import shutil
import subprocess
from pathlib import Path

# ============ User configuration (may be modified to suit your specific environment)============
CHARGEMOL_EXEC = "/home/user/bin/Chargemol_09_26_2017_linux_parallel"
DEFAULT_ATOMIC_DENSITIES = "/home/user/bin/atomic_densities/"
SBATCH_CONFIG = {
    "partition": "CPU",
    "nodes": 1,
    "ntasks_per_node": 4,
    "time": "01:00:00",
}
# ======================================================


def clean_potcar(potcar_path):
    """Delete all lines in POTCAR that contain “SHA256” or 'COPYR' 的行"""
    with open(potcar_path, 'r') as f:
        lines = f.readlines()
    with open(potcar_path, 'w') as f:
        for line in lines:
            if 'SHA256' not in line and 'COPYR' not in line:
                f.write(line)


def create_job_control(run_dir, atom_dens_dir, input_filename):
    """Generate job_control.txt"""
    content = f""".true.
.true.
.true.
</periodicity along A, B, and C vectors>

<atomic densities directory complete path>
{atom_dens_dir}
</atomic densities directory complete path>

<input filename>
{input_filename}
</input filename>

<charge type>
DDEC6
</charge type>
"""
    job_control_path = run_dir / "job_control.txt"
    with open(job_control_path, 'w') as f:
        f.write(content)


def create_submit_script(run_dir, job_name, exec_path, sbatch_conf):
    """Generate a SLURM submission script"""
    script = f"""#!/bin/bash
#SBATCH --job-name="{job_name}"
#SBATCH --output="{job_name}.o%j.%N.out"
#SBATCH --partition={sbatch_conf["partition"]}
#SBATCH --nodes {sbatch_conf["nodes"]}
#SBATCH --ntasks-per-node={sbatch_conf["ntasks_per_node"]}
#SBATCH --export=ALL
#SBATCH -t {sbatch_conf["time"]}

export OMP_NUM_THREADS={sbatch_conf["ntasks_per_node"]}
module load gnu

cd "$SLURM_SUBMIT_DIR"

{exec_path}

echo "run complete on `hostname`: `date`" 1>&2
"""
    script_path = run_dir / "submit.slurm"
    with open(script_path, 'w') as f:
        f.write(script)
    script_path.chmod(0o755)


def process_folder(folder_path, atom_dens_dir, submit_flag):
    """
    Processing a single folder (absolute path or Path object)
    """
    folder_name = folder_path.name
    print(f"Process folder：{folder_name}")

    # Checking the required documents
    required = ["AECCAR0", "AECCAR2", "CHGCAR", "POTCAR"]
    missing = [f for f in required if not (folder_path / f).is_file()]
    if missing:
        print(f"  Warning: Missing file {', '.join(missing)}, skip this folder")
        return

    # Create a working directory
    run_dir = folder_path / "DDEC6_run"
    run_dir.mkdir(exist_ok=True)

    # Copy files
    for f in required:
        src = folder_path / f
        dst = run_dir / f
        shutil.copy2(src, dst)
    print(f"  The file has been copied to {run_dir}")

    # Clean up POTCAR
    potcar_copy = run_dir / "POTCAR"
    clean_potcar(potcar_copy)
    print("  POTCAR Cleared")

    # Generate a job_control.txt
    create_job_control(run_dir, atom_dens_dir, folder_name)
    print(f"  job_control.txt generated（Fold name：{folder_name}）")

    # Generate a submission script
    job_name = f"DDEC6_{folder_name}"
    create_submit_script(run_dir, job_name, CHARGEMOL_EXEC, SBATCH_CONFIG)
    print(f"  Submission script generated：{run_dir / 'submit.slurm'}")

    # If you need to submit
    if submit_flag:
        try:
            result = subprocess.run(
                ["sbatch", "submit.slurm"],
                cwd=str(run_dir),
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                print(f"  The assignment has been submitted（{folder_name}）")
            else:
                print(f"  Submission failed（{folder_name}）：{result.stderr.strip()}")
        except Exception as e:
            print(f"  An exception occurred during submission：{e}")

    print("-" * 30)


def main():
    parser = argparse.ArgumentParser(
        description="Batch preparation DDEC6 Charge calculation (recursive search for VASP folders in all subdirectories)"
    )
    parser.add_argument(
        "atom_dens_dir",
        nargs="?",
        default=DEFAULT_ATOMIC_DENSITIES,
        help="The full path to the atomic density directory (the default value is specified in the configuration)"
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit all assignments as soon as you have finished preparing them"
    )
    args = parser.parse_args()

    atom_dens_dir = Path(args.atom_dens_dir).resolve()

    atom_dens_dir_str = str(atom_dens_dir) + '/'
    # Then pass `atom_dens_dir_str` to `process_folder`, rather than a `Path` object
    
    if not atom_dens_dir.is_dir():
        print(f"Error: The ‘atomic density’ directory does not exist: {atom_dens_dir}")
        sys.exit(1)

    exec_path = Path(CHARGEMOL_EXEC)
    if not exec_path.is_file() or not os.access(exec_path, os.X_OK):
        print(f"Error: The Chargemol executable file does not exist or is not executable: {exec_path}")
        sys.exit(1)

    current_dir = Path.cwd()
    print(f"Root：{current_dir}")

    # Recursively traverse all subdirectories
    processed_count = 0
    for dirpath, dirnames, filenames in os.walk(current_dir):
        dir_path = Path(dirpath)
        # Skip the DDEC6_run directory (to avoid searching within it again)
        if dir_path.name == "DDEC6_run":
            continue

        # Check that all four required files are included
        required_set = {"AECCAR0", "AECCAR2", "CHGCAR", "POTCAR"}
        if required_set.issubset(set(filenames)):
            process_folder(dir_path, atom_dens_dir_str, args.submit)
            processed_count += 1

    print(f"All folders have been processed! A total of  {processed_count} valid folders。")
    if not args.submit:
        print("To submit your assignment, please run the following command in each DDEC6_run directory: sbatch submit.slurm")
        print("Alternatively, run this script again and add the --submit parameter")


if __name__ == "__main__":
    main()

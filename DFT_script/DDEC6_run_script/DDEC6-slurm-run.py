#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_ddec6_batch.py - 批量准备 DDEC6 电荷计算（支持递归查找子文件夹）
用法:
    ./run_ddec6_batch.py [原子密度目录] [--submit]
示例:
    ./run_ddec6_batch.py /home/naturegogo/bin/atomic_densities/ --submit
"""

import os
import sys
import argparse
import shutil
import subprocess
from pathlib import Path

# ============ 用户配置（可根据实际环境修改）============
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
    """删除 POTCAR 中所有包含 'SHA256' 或 'COPYR' 的行"""
    with open(potcar_path, 'r') as f:
        lines = f.readlines()
    with open(potcar_path, 'w') as f:
        for line in lines:
            if 'SHA256' not in line and 'COPYR' not in line:
                f.write(line)


def create_job_control(run_dir, atom_dens_dir, input_filename):
    """生成 job_control.txt"""
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
    """生成 SLURM 提交脚本"""
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
    处理单个文件夹（绝对路径或 Path 对象）
    """
    folder_name = folder_path.name
    print(f"处理文件夹：{folder_name}")

    # 检查必备文件
    required = ["AECCAR0", "AECCAR2", "CHGCAR", "POTCAR"]
    missing = [f for f in required if not (folder_path / f).is_file()]
    if missing:
        print(f"  警告：缺少文件 {', '.join(missing)}，跳过该文件夹")
        return

    # 创建运行目录
    run_dir = folder_path / "DDEC6_run"
    run_dir.mkdir(exist_ok=True)

    # 复制文件
    for f in required:
        src = folder_path / f
        dst = run_dir / f
        shutil.copy2(src, dst)
    print(f"  文件已复制到 {run_dir}")

    # 清理 POTCAR
    potcar_copy = run_dir / "POTCAR"
    clean_potcar(potcar_copy)
    print("  POTCAR 已清理")

    # 生成 job_control.txt
    create_job_control(run_dir, atom_dens_dir, folder_name)
    print(f"  job_control.txt 已生成（基名：{folder_name}）")

    # 生成提交脚本
    job_name = f"DDEC6_{folder_name}"
    create_submit_script(run_dir, job_name, CHARGEMOL_EXEC, SBATCH_CONFIG)
    print(f"  提交脚本已生成：{run_dir / 'submit.slurm'}")

    # 若需要提交
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
                print(f"  作业已提交（{folder_name}）")
            else:
                print(f"  提交失败（{folder_name}）：{result.stderr.strip()}")
        except Exception as e:
            print(f"  提交时发生异常：{e}")

    print("-" * 30)


def main():
    parser = argparse.ArgumentParser(
        description="批量准备 DDEC6 电荷计算（递归查找所有子目录中的 VASP 文件夹）"
    )
    parser.add_argument(
        "atom_dens_dir",
        nargs="?",
        default=DEFAULT_ATOMIC_DENSITIES,
        help="原子密度目录的完整路径（默认为配置中的默认值）"
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="准备完成后立即提交所有作业"
    )
    args = parser.parse_args()

    atom_dens_dir = Path(args.atom_dens_dir).resolve()

    atom_dens_dir_str = str(atom_dens_dir) + '/'
    # 然后传递 atom_dens_dir_str 给 process_folder，而不是 Path 对象
    
    if not atom_dens_dir.is_dir():
        print(f"错误：原子密度目录不存在：{atom_dens_dir}")
        sys.exit(1)

    exec_path = Path(CHARGEMOL_EXEC)
    if not exec_path.is_file() or not os.access(exec_path, os.X_OK):
        print(f"错误：Chargemol 可执行文件不存在或不可执行：{exec_path}")
        sys.exit(1)

    current_dir = Path.cwd()
    print(f"根目录：{current_dir}")

    # 递归遍历所有子目录
    processed_count = 0
    for dirpath, dirnames, filenames in os.walk(current_dir):
        dir_path = Path(dirpath)
        # 跳过 DDEC6_run 目录（避免在其内部再次查找）
        if dir_path.name == "DDEC6_run":
            continue

        # 检查是否同时包含四个必需文件
        required_set = {"AECCAR0", "AECCAR2", "CHGCAR", "POTCAR"}
        if required_set.issubset(set(filenames)):
            process_folder(dir_path, atom_dens_dir_str, args.submit)
            processed_count += 1

    print(f"所有文件夹处理完成！共处理 {processed_count} 个有效文件夹。")
    if not args.submit:
        print("如需提交作业，请在每个 DDEC6_run 目录中执行：sbatch submit.slurm")
        print("或再次运行本脚本并添加 --submit 参数")


if __name__ == "__main__":
    main()
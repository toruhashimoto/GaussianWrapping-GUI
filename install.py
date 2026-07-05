"""GaussianWrapping GUI - full automated installer for Windows.

Run via install.bat. Steps (each is idempotent - rerun after a failure and
completed steps are skipped):

  1. prerequisite checks (NVIDIA GPU arch, CUDA 12.8, VS2022 Build Tools, conda)
  2. conda env (python 3.11) + torch 2.9.1+cu128
  3. clone the Windows fork of GaussianWrapping (branch: windows, recursive)
  4. apply the nvdiffrast torch-2.9 patch (submodule, cannot live in the fork)
  5. python requirements
  6. build 7 CUDA extensions (pip, with NVCC_APPEND_FLAGS=-DUSE_CUDA)
  7. CGAL via conda-forge + build tetra_triangulation (Ninja)
  8. write config.json + smoke test

Total time: roughly 30-60 minutes depending on the machine.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORK_URL = "https://github.com/toruhashimoto/GaussianWrapping.git"
FORK_BRANCH = "windows"
GW_DIR = os.path.join(HERE, "GaussianWrapping")
CONFIG = os.path.join(HERE, "config.json")
TORCH_SPEC = ["torch==2.9.1", "torchvision==0.24.1",
              "--index-url", "https://download.pytorch.org/whl/cu128"]
CUDA_DEFAULT = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8"
VCVARS_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
]
EXTENSIONS = [  # pip-buildable CUDA extensions, in build order
    "submodules/diff-gaussian-rasterization",
    "submodules/diff-gaussian-rasterization_ms",
    "submodules/diff-gaussian-rasterization_ours",
    "submodules/diff-gaussian-rasterization_sof",
    "submodules/simple-knn",
    "submodules/fused-ssim",
    "submodules/Geometry-Grounded-Gaussian-Splatting/submodules/warp-patch-ncc",
]


def log(msg):
    print(msg, flush=True)


def die(msg):
    log(f"\n[ERROR] {msg}")
    sys.exit(1)


def run(cmd, env=None, cwd=None, check=True, capture=False):
    log(f"  $ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, env=env, cwd=cwd, text=True,
                       capture_output=capture, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        if capture:
            log((r.stdout or "")[-4000:])
            log((r.stderr or "")[-4000:])
        die(f"command failed (exit {r.returncode}): {' '.join(str(c) for c in cmd)}")
    return r


# ---------------------------------------------------------------- step 1
def detect_gpu_arch(override):
    if override:
        return override
    smi = shutil.which("nvidia-smi")
    if not smi:
        die("nvidia-smi not found - an NVIDIA GPU driver is required.\n"
            "Install the latest driver from https://www.nvidia.com/drivers")
    r = run([smi, "--query-gpu=compute_cap,name", "--format=csv,noheader"],
            capture=True, check=False)
    m = re.match(r"\s*(\d+)\.(\d+)\s*,\s*(.+)", (r.stdout or "").splitlines()[0] if r.stdout else "")
    if not m:
        die("could not detect GPU compute capability.\n"
            "Re-run with:  install.bat --arch <X.Y>   (e.g. 12.0 for RTX 50xx, "
            "8.9 for RTX 40xx, 8.6 for RTX 30xx)")
    arch = f"{m.group(1)}.{m.group(2)}"
    name = m.group(3).strip()
    log(f"[OK] GPU: {name} (compute capability {arch})")
    if float(arch) < 8.0:
        die(f"GPU arch sm_{arch.replace('.', '')} is below the supported range "
            "(RTX 30-series / sm_80 or newer).")
    return arch


def detect_cuda(override):
    cand = [override] if override else [os.environ.get("CUDA_PATH_V12_8"), CUDA_DEFAULT]
    for c in cand:
        if c and os.path.isfile(os.path.join(c, "bin", "nvcc.exe")):
            log(f"[OK] CUDA Toolkit 12.8: {c}")
            return c
    die("CUDA Toolkit 12.8 not found.\n"
        "Download: https://developer.nvidia.com/cuda-12-8-0-download-archive\n"
        "(12.8 specifically - it must match the torch cu128 wheels. "
        "Other versions may coexist; 12.8 just needs to be installed.)")


def detect_vcvars(override):
    for c in ([override] if override else VCVARS_CANDIDATES):
        if c and os.path.isfile(c):
            log(f"[OK] VS2022 vcvars64: {c}")
            return c
    die("Visual Studio 2022 Build Tools not found.\n"
        "Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/\n"
        'Install the "Desktop development with C++" workload.')


def detect_conda(override):
    cand = [override, shutil.which("conda"),
            os.path.expandvars(r"%USERPROFILE%\miniconda3\Scripts\conda.exe"),
            os.path.expandvars(r"%USERPROFILE%\anaconda3\Scripts\conda.exe"),
            r"C:\ProgramData\miniconda3\Scripts\conda.exe"]
    for c in cand:
        if c and os.path.isfile(c):
            log(f"[OK] conda: {c}")
            return c
    die("conda not found (needed for the Python env and the CGAL library).\n"
        "Install Miniconda: https://docs.conda.io/en/latest/miniconda.html")


# ---------------------------------------------------------------- step 2
def env_python(conda, env_name):
    r = run([conda, "info", "--base"], capture=True)
    base = r.stdout.strip().splitlines()[-1].strip()
    return os.path.join(base, "envs", env_name, "python.exe")


def ensure_env(conda, env_name):
    py = env_python(conda, env_name)
    if os.path.isfile(py):
        log(f"[SKIP] conda env '{env_name}' already exists")
        return py
    log(f"[STEP] creating conda env '{env_name}' (python 3.11)")
    run([conda, "create", "-n", env_name, "python=3.11", "-y"])
    return py


def ensure_torch(py):
    r = run([py, "-c", "import torch; print(torch.__version__)"],
            capture=True, check=False)
    if r.returncode == 0 and "2.9.1+cu128" in (r.stdout or ""):
        log("[SKIP] torch 2.9.1+cu128 already installed")
        return
    log("[STEP] installing torch 2.9.1+cu128 (~3 GB download)")
    run([py, "-m", "pip", "install"] + TORCH_SPEC)
    r = run([py, "-c", "import torch; print(torch.cuda.get_arch_list())"], capture=True)
    log(f"  torch arch list: {r.stdout.strip()}")


# ---------------------------------------------------------------- step 3
def ensure_fork():
    if os.path.isdir(os.path.join(GW_DIR, ".git")):
        log("[SKIP] GaussianWrapping fork already cloned")
        return
    log(f"[STEP] cloning {FORK_URL} (branch {FORK_BRANCH}, with submodules)")
    run(["git", "clone", "--recurse-submodules", "--branch", FORK_BRANCH,
         FORK_URL, GW_DIR])


# ---------------------------------------------------------------- step 4
def patch_nvdiffrast():
    """torch 2.9: JIT modules are no longer auto-registered in sys.modules.

    nvdiffrast is a git submodule pinned to upstream, so this cannot live in
    the fork; apply it idempotently after checkout.
    """
    ops = os.path.join(GW_DIR, "submodules", "nvdiffrast", "nvdiffrast", "torch", "ops.py")
    with open(ops, encoding="utf-8") as f:
        src = f.read()
    if "_sys.modules.setdefault" in src:
        log("[SKIP] nvdiffrast already patched")
        return
    old_load = ("    torch.utils.cpp_extension.load(name=plugin_name, sources=source_paths, "
                "extra_cflags=common_opts+cc_opts, extra_cuda_cflags=common_opts+['-lineinfo'], "
                "extra_ldflags=ldflags, with_cuda=True, verbose=False)")
    new_load = old_load.replace("    torch.utils", "    plugin = torch.utils")
    old_import = "    _cached_plugin[gl] = importlib.import_module(plugin_name)"
    new_import = ("    import sys as _sys  # torch 2.9: use load()'s return value\n"
                  "    _sys.modules.setdefault(plugin_name, plugin)\n"
                  "    _cached_plugin[gl] = plugin")
    if old_load not in src or old_import not in src:
        die("nvdiffrast ops.py does not match the expected upstream content - "
            "the submodule may have been updated. Please open an issue.")
    src = src.replace(old_load, new_load).replace(old_import, new_import)
    with open(ops, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    log("[OK] nvdiffrast ops.py patched for torch 2.9")


# ---------------------------------------------------------------- steps 5-7
def build_env_vars(cuda_home, arch, env_py):
    env = os.environ.copy()
    prefix = os.path.dirname(env_py)
    env.update({
        "CUDA_HOME": cuda_home, "CUDA_PATH": cuda_home,
        "TORCH_CUDA_ARCH_LIST": arch,
        "DISTUTILS_USE_SDK": "1", "VSLANG": "1033",
        "NVCC_APPEND_FLAGS": "-DUSE_CUDA",
        "PYTHONUTF8": "1",
        "PATH": os.path.join(cuda_home, "bin") + ";" +
                os.path.join(prefix, "Scripts") + ";" +
                os.path.join(prefix, "Library", "bin") + ";" + env["PATH"],
    })
    return env


def run_in_vcvars(vcvars, inner_cmd, env, cwd=None):
    """cl/nvcc need the VS environment; chain through vcvars64.bat."""
    quoted = subprocess.list2cmdline(inner_cmd)
    return subprocess.run(f'call "{vcvars}" >nul 2>nul && {quoted}',
                          shell=True, env=env, cwd=cwd).returncode


def ensure_requirements(py):
    log("[STEP] python requirements (open3d, trimesh, gradio, ...)")
    run([py, "-m", "pip", "install", "-r",
         os.path.join(GW_DIR, "requirements.txt")])
    run([py, "-m", "pip", "install", "-r",
         os.path.join(HERE, "requirements-gui.txt")])
    run([py, "-m", "pip", "install", "ninja", "wheel"])


def module_ok(py, module):
    return run([py, "-c", f"import {module}"], capture=True, check=False).returncode == 0


def ensure_extensions(py, vcvars, env):
    mods = {  # pip dir -> import name
        "submodules/diff-gaussian-rasterization": "diff_gaussian_rasterization",
        "submodules/diff-gaussian-rasterization_ms": "diff_gaussian_rasterization_ms",
        "submodules/diff-gaussian-rasterization_ours": "diff_gaussian_rasterization_ours",
        "submodules/diff-gaussian-rasterization_sof": "diff_gaussian_rasterization_sof",
        "submodules/simple-knn": "simple_knn",
        "submodules/fused-ssim": "fused_ssim",
        "submodules/Geometry-Grounded-Gaussian-Splatting/submodules/warp-patch-ncc": "warp_patch_ncc",
    }

    for i, sub in enumerate(EXTENSIONS, 1):
        name = mods[sub]
        if name and module_ok(py, name):
            log(f"[SKIP] ({i}/{len(EXTENSIONS)}) {name} already installed")
            continue
        log(f"[STEP] ({i}/{len(EXTENSIONS)}) building {sub} (several minutes)")
        rc = run_in_vcvars(vcvars, [py, "-m", "pip", "install",
                                    "--no-build-isolation",
                                    os.path.join(GW_DIR, *sub.split("/"))], env)
        if rc != 0:
            die(f"building {sub} failed (exit {rc}). "
                "Scroll up for the compiler error; please open an issue with it.")
    # nvdiffrast is a plain python install (JIT-compiles at first use)
    if not module_ok(py, "nvdiffrast"):
        log("[STEP] installing nvdiffrast (python package; compiles at first use)")
        rc = run_in_vcvars(vcvars, [py, "-m", "pip", "install", "--no-build-isolation",
                                    os.path.join(GW_DIR, "submodules", "nvdiffrast")], env)
        if rc != 0:
            die("installing nvdiffrast failed")


def ensure_tetra(py, conda, env_name, vcvars, env, arch):
    if module_ok(py, "tetranerf.utils.extension"):
        log("[SKIP] tetra_triangulation already installed")
        return
    log("[STEP] CGAL/GMP/MPFR via conda-forge")
    run([conda, "install", "-n", env_name, "-y", "-c", "conda-forge",
         "cgal-cpp", "gmp", "mpfr", "cmake", "ninja"])
    src = os.path.join(GW_DIR, "submodules", "tetra_triangulation")
    prefix = os.path.dirname(py)
    log("[STEP] building tetra_triangulation (CGAL Delaunay, Ninja)")
    for f in ["CMakeCache.txt"]:
        p = os.path.join(src, f)
        if os.path.exists(p):
            os.remove(p)
    cmake = os.path.join(prefix, "Library", "bin", "cmake.exe")
    if not os.path.isfile(cmake):
        cmake = "cmake"
    arch_flat = arch.replace(".", "")
    rc = run_in_vcvars(vcvars, [
        cmake, "-G", "Ninja", "-S", ".", "-B", ".",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",
        f"-DCMAKE_PREFIX_PATH={prefix}\\Lib\\site-packages\\torch\\share\\cmake;{prefix}\\Library\\lib\\cmake;{prefix}\\Library",
        f"-DCGAL_DIR={prefix}\\Library\\lib\\cmake\\CGAL",
        f"-DTORCH_PYTHON_LIBRARY={prefix}\\Lib\\site-packages\\torch\\lib\\torch_python.lib",
        f"-DPython_EXECUTABLE={py}", f"-DPYTHON_EXECUTABLE={py}",
        f"-DCMAKE_CUDA_ARCHITECTURES={arch_flat}",
        f"-DCONDA_PREFIX={prefix}\\Library"], env, cwd=src)
    if rc != 0:
        die("tetra_triangulation cmake configure failed. The pipeline still "
            "works with '--delaunay_method scipy' - see docs/troubleshooting.")
    rc = run_in_vcvars(vcvars, [cmake, "--build", "."], env, cwd=src)
    if rc != 0:
        die("tetra_triangulation build failed (see docs/troubleshooting; "
            "scipy fallback is available)")
    run([py, "-m", "pip", "install", "-e", src])


# ---------------------------------------------------------------- step 8
def write_config(py, cuda_home, vcvars, arch, conda, env_name):
    cfg = {"env_python": py, "gw_repo": GW_DIR, "cuda_home": cuda_home,
           "vcvars": vcvars, "arch": arch, "conda": conda, "env_name": env_name}
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    log(f"[OK] wrote {CONFIG}")
    # plain SET lines for the .bat launchers (no JSON parsing in cmd.exe)
    env_bat = os.path.join(HERE, "launch_env.bat")
    with open(env_bat, "w", encoding="ascii", newline="\r\n") as f:
        f.write("@echo off\n"
                "REM Generated by install.py - do not edit (re-run install.bat instead).\n"
                f'set "PY={py}"\n'
                f'set "VCVARS={vcvars}"\n'
                f'set "CUDA_HOME={cuda_home}"\n'
                f'set "TORCH_CUDA_ARCH_LIST={arch}"\n')
    log(f"[OK] wrote {env_bat}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-name", default="gwgui")
    ap.add_argument("--arch", default=None, help="GPU compute capability, e.g. 12.0")
    ap.add_argument("--cuda", default=None, help="CUDA 12.8 install dir")
    ap.add_argument("--vcvars", default=None, help="path to vcvars64.bat")
    ap.add_argument("--conda", default=None, help="path to conda.exe")
    args = ap.parse_args()

    log("=" * 64)
    log("GaussianWrapping GUI installer")
    log("=" * 64)
    arch = detect_gpu_arch(args.arch)
    cuda_home = detect_cuda(args.cuda)
    vcvars = detect_vcvars(args.vcvars)
    conda = detect_conda(args.conda)

    py = ensure_env(conda, args.env_name)
    ensure_torch(py)
    ensure_fork()
    patch_nvdiffrast()
    ensure_requirements(py)
    env = build_env_vars(cuda_home, arch, py)
    ensure_extensions(py, vcvars, env)
    ensure_tetra(py, conda, args.env_name, vcvars, env, arch)
    write_config(py, cuda_home, vcvars, arch, conda, args.env_name)

    log("[STEP] smoke test")
    rc = run_in_vcvars(vcvars, [py, os.path.join(HERE, "smoke_test.py")], env, cwd=HERE)
    if rc != 0:
        die("smoke test failed - see the list above for the failing component")
    log("")
    log("=" * 64)
    log("INSTALL COMPLETE. Start the app with launch_gui.bat")
    log("=" * 64)


if __name__ == "__main__":
    main()

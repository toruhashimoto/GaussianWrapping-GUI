"""GaussianWrapping GUI - command line interface.

Faithful to upstream: `gw.py run` forwards every unrecognized flag verbatim to
GaussianWrapping's own `train_and_extract_gw_{ours,radegs}.py`. The GUI uses
exactly this module to build and run its commands, so GUI and CLI cannot
diverge.

  gw.py run -s <COLMAP_DATASET> -m <OUTPUT_DIR> [--quality fast|best|high]
            [--rasterizer ours|radegs] [--vram 8|12|16|24|48|96]
            [any upstream flag ...]
  gw.py doctor          # environment smoke test
  gw.py check -s <DIR>  # validate a COLMAP dataset folder
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")

# --N_max_gaussians presets: 24 GB matches the upstream default (6M);
# 48/96 GB (workstation cards, e.g. RTX PRO 6000) scale that cap by VRAM ratio.
# These are OOM-prevention caps, not targets - densification only reaches them
# on large scenes.
VRAM_PRESETS = {"8": 1_200_000, "12": 1_800_000, "16": 2_500_000,
                "24": 6_000_000, "48": 12_000_000, "96": 24_000_000}

# Quality presets, built only from upstream-documented knobs:
#   fast = ours rasterizer (faster, better metrics per upstream README)
#   best = radegs rasterizer (smoother-looking meshes)
#   high = radegs + full input resolution (-r 1 disables the automatic
#          1600px downscale) + --isosurface_value 0.2 (upstream's
#          recommendation when fine details are missing). Slowest, most VRAM.
QUALITY_PRESETS = {
    "fast": {"rasterizer": "ours", "flags": []},
    "best": {"rasterizer": "radegs", "flags": []},
    "high": {"rasterizer": "radegs",
             "flags": ["-r", "1", "--isosurface_value", "0.2"]},
}


def load_config():
    if not os.path.isfile(CONFIG):
        raise SystemExit("[ERROR] config.json not found - run install.bat first")
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def runtime_env(cfg):
    env = os.environ.copy()
    prefix = os.path.dirname(cfg["env_python"])
    env.update({
        "CUDA_HOME": cfg["cuda_home"], "CUDA_PATH": cfg["cuda_home"],
        "TORCH_CUDA_ARCH_LIST": cfg["arch"],
        "DISTUTILS_USE_SDK": "1", "VSLANG": "1033",
        "NVCC_APPEND_FLAGS": "-DUSE_CUDA",
        "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
        "PATH": os.path.join(cfg["cuda_home"], "bin") + ";" +
                os.path.join(prefix, "Scripts") + ";" +
                os.path.join(prefix, "Library", "bin") + ";" + env["PATH"],
    })
    return env


def check_dataset(path):
    """Validate a COLMAP dataset folder. Returns (ok, list of messages)."""
    msgs = []
    ok = True
    if not path or not os.path.isdir(path):
        return False, [f"NG: folder not found: {path!r}"]
    img_dir = os.path.join(path, "images")
    if os.path.isdir(img_dir):
        n_img = len([f for f in os.listdir(img_dir)
                     if f.lower().endswith((".jpg", ".jpeg", ".png"))])
        if n_img:
            msgs.append(f"OK: images/ with {n_img} images")
        else:
            ok = False
            msgs.append("NG: images/ contains no jpg/png images")
    else:
        ok = False
        msgs.append("NG: images/ folder missing")
    sparse = None
    for cand in [os.path.join(path, "sparse", "0"), os.path.join(path, "sparse")]:
        if (os.path.isfile(os.path.join(cand, "cameras.txt"))
                or os.path.isfile(os.path.join(cand, "cameras.bin"))):
            sparse = cand
            break
    if sparse is None:
        return False, msgs + ["NG: sparse/(0/) with cameras.txt|bin missing - "
                              "export the registration in COLMAP format"]
    msgs.append(f"OK: sparse model at {os.path.relpath(sparse, path)}")
    cam_txt = os.path.join(sparse, "cameras.txt")
    if os.path.isfile(cam_txt):
        with open(cam_txt, encoding="utf-8", errors="replace") as f:
            models = {ln.split()[1] for ln in f
                      if ln.strip() and not ln.startswith("#") and len(ln.split()) > 1}
        bad = models - {"PINHOLE", "SIMPLE_PINHOLE"}
        if bad:
            ok = False
            msgs.append(f"NG: unsupported camera model(s) {sorted(bad)} - "
                        "export undistorted images with a PINHOLE model")
        else:
            msgs.append(f"OK: camera model {sorted(models)}")
    return ok, msgs


def build_run_command(cfg, source, output, quality="fast", vram="16",
                      resolution=None, isosurface=None, extra=(),
                      rasterizer=None):
    """Build the exact upstream command. Extra flags go through verbatim, last
    occurrence wins in upstream argparse, so user flags override presets
    (order: quality-preset flags -> advanced fields -> extra)."""
    preset = QUALITY_PRESETS[quality]
    script = os.path.join(cfg["gw_repo"], "gaussian_wrapping", "scripts",
                          f"train_and_extract_gw_{rasterizer or preset['rasterizer']}.py")
    cmd = [cfg["env_python"], script, "-s", source, "-m", output,
           "--N_max_gaussians", str(VRAM_PRESETS[str(vram)])]
    cmd += preset["flags"]
    if resolution and int(resolution) > 0:
        cmd += ["-r", str(int(resolution))]
    if isosurface is not None and str(isosurface) != "":
        cmd += ["--isosurface_value", str(isosurface)]
    cmd += list(extra)
    return cmd


def cmd_run(argv):
    ap = argparse.ArgumentParser(prog="gw.py run", add_help=False)
    ap.add_argument("-s", "--source_path", required=True)
    ap.add_argument("-m", "--model_path", required=True)
    ap.add_argument("--quality", choices=list(QUALITY_PRESETS), default="fast")
    ap.add_argument("--rasterizer", choices=["ours", "radegs"], default=None,
                    help="explicit rasterizer (overrides the quality preset's)")
    ap.add_argument("--vram", choices=list(VRAM_PRESETS), default="16")
    args, extra = ap.parse_known_args(argv)

    ok, msgs = check_dataset(args.source_path)
    for m in msgs:
        print("  " + m)
    if not ok:
        raise SystemExit("[ERROR] dataset validation failed (see above)")

    cfg = load_config()
    cmd = build_run_command(cfg, args.source_path, args.model_path,
                            args.quality, args.vram, extra=extra,
                            rasterizer=args.rasterizer)
    print("[INFO] " + subprocess.list2cmdline(cmd))
    r = subprocess.run(cmd, env=runtime_env(cfg), cwd=cfg["gw_repo"])
    raise SystemExit(r.returncode)


def cmd_doctor():
    cfg = load_config()
    r = subprocess.run([cfg["env_python"], os.path.join(HERE, "smoke_test.py")],
                       env=runtime_env(cfg), cwd=HERE)
    raise SystemExit(r.returncode)


def cmd_check(argv):
    ap = argparse.ArgumentParser(prog="gw.py check")
    ap.add_argument("-s", "--source_path", required=True)
    args = ap.parse_args(argv)
    ok, msgs = check_dataset(args.source_path)
    for m in msgs:
        print("  " + m)
    raise SystemExit(0 if ok else 1)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "doctor", "check"):
        print(__doc__)
        raise SystemExit(1)
    if sys.argv[1] == "run":
        cmd_run(sys.argv[2:])
    elif sys.argv[1] == "doctor":
        cmd_doctor()
    else:
        cmd_check(sys.argv[2:])


if __name__ == "__main__":
    main()

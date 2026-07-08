# GaussianWrapping GUI

![Status: Beta](https://img.shields.io/badge/status-beta-orange)
![Platform: Windows](https://img.shields.io/badge/platform-Windows%2011-blue)
![License: Non--commercial research](https://img.shields.io/badge/license-non--commercial%20research-lightgrey)

**A Windows desktop app (and faithful CLI) for [Gaussian Wrapping](https://github.com/diego1401/GaussianWrapping) — turn a RealityScan / COLMAP export into a high-quality mesh with a one-shot installer and a two-clicks GUI.**

[日本語版 README はこちら / Japanese README](README.ja.md)

> [!WARNING]
> **Beta.** Validated end-to-end on Windows 11 + RTX 5070 Ti (Blackwell).
> RTX 30/40-series should work with the same recipe (the installer detects
> your GPU architecture) but are **not yet tested on real hardware**.
> Feedback via GitHub Issues is very welcome.

Workflow: **RealityScan → COLMAP export → this GUI → mesh (PLY)**. Pairs well
with [rs-gw-mesh-fusion](https://github.com/toruhashimoto/rs-gw-mesh-fusion)
to fuse the result with your RealityScan High Detail mesh into one model.

## Prerequisites (install once, ~15 min)

| What | Where | Notes |
|---|---|---|
| NVIDIA driver | https://www.nvidia.com/drivers | RTX 30/40/50 series (sm_80+) |
| CUDA Toolkit **12.8** | https://developer.nvidia.com/cuda-12-8-0-download-archive | exactly 12.8 (matches the torch cu128 wheels); it can coexist with other versions |
| VS2022 Build Tools | https://visualstudio.microsoft.com/visual-cpp-build-tools/ | check "Desktop development with C++" |
| Python **3.11** | https://www.python.org/downloads/release/python-311/ | required for the conda-free installer (recommended) |
| Miniconda | https://docs.conda.io/en/latest/miniconda.html | conda install path only; provides CGAL via conda-forge |

## Install (conda-free, recommended for restricted PCs)

This path uses a local Python venv and pip only. It skips the CGAL
`tetra_triangulation` extension and automatically runs mesh extraction with
`--delaunay_method scipy`. The Delaunay step is slower, but setup avoids
Miniconda and conda-forge entirely. **The CUDA extension builds still happen**
exactly as in the conda path, so CUDA 12.8 and VS2022 Build Tools are still
required.

```bat
git clone https://github.com/toruhashimoto/GaussianWrapping-GUI
cd GaussianWrapping-GUI
install_venv.bat
```

After a successful install, use the same launchers as usual:

```bat
launch_gui.bat
gw_run.bat doctor
```

## Install (full conda + CGAL, faster Delaunay)

```bat
git clone https://github.com/toruhashimoto/GaussianWrapping-GUI
cd GaussianWrapping-GUI
install.bat
```

The installer checks the prerequisites (and tells you exactly what is missing),
creates a conda env, installs torch 2.9.1+cu128, clones the
[Windows fork of Gaussian Wrapping](https://github.com/toruhashimoto/GaussianWrapping)
(branch `windows`), builds all CUDA extensions with the correct environment
(`NVCC_APPEND_FLAGS=-DUSE_CUDA` — see the fork's `WINDOWS.md` for why), builds
the CGAL Delaunay extension, and finishes with a smoke test. **Re-running
`install.bat` after a failure skips completed steps.**

Use this full path when Miniconda is acceptable and you want the faster
CGAL/tetra_triangulation Delaunay backend.

## Use — GUI

Double-click `launch_gui.bat`. Pick your **COLMAP dataset folder**
(`images/` + `sparse/`; the GUI validates it and tells you what's wrong if
anything), pick an **output folder**, choose a quality preset
(`fast`, `best`, or `high` = radegs + full resolution + isosurface 0.2), your
**GPU VRAM** (sets the Gaussian cap), an **input resolution** (auto / full /
½ / ¼), and whether to **remove background & floaters** (on by default — keeps
only the largest connected part of the mesh; disconnected pieces only),
press **Run**. The three stages (training → mesh extraction → texture
refinement) stream their logs into the window; when done you get the mesh
paths and rendered previews. A **Diagnostics** tab re-runs the environment
smoke test any time.

Expect roughly 1–1.5 h for a ~70-photo scene on an RTX 5070 Ti.

## Use — CLI (faithful to upstream)

```bat
gw_run.bat run -s C:\data\my_scan -m C:\data\my_scan_out --rasterizer ours --vram 16
```

Anything the wrapper does not recognize is **passed to the upstream
`train_and_extract_gw_*.py` verbatim** (and, since upstream argparse lets the
last occurrence win, your flags override the presets):

```bat
gw_run.bat run -s ... -m ... --vram 16 -r 2 --isosurface_value 0.2 --no_postprocess
gw_run.bat doctor          &REM environment smoke test
gw_run.bat check -s DIR    &REM validate a dataset folder only
```

The GUI builds its commands through the exact same code path, so GUI and CLI
never diverge.

## Dataset requirements

- COLMAP layout: `images/` + `sparse/0/` (or `sparse/`) with
  `cameras/images/points3D` as `.txt` or `.bin` (RealityScan's text-only
  export works — that's one of the fork's patches).
- PINHOLE camera model (undistorted images). RealityScan's COLMAP export
  satisfies this.

## Sample data

A 74-photo sample dataset (RealityScan COLMAP export) is attached to the
[latest release](https://github.com/toruhashimoto/GaussianWrapping-GUI/releases)
as `Sample_COLMAP.zip` — unzip and point the GUI at it for a first run.

## Troubleshooting

- **`error C2872: 'std': ambiguous symbol` during install** — you are building
  without `NVCC_APPEND_FLAGS=-DUSE_CUDA`; use `install.bat` (it sets it), don't
  build by hand.
- **tetra_triangulation build fails** — the pipeline still works: add
  `--delaunay_method scipy` to the extra args (slower Delaunay step), or run
  `install_venv.bat` for the conda-free scipy fallback profile.
- **First run is slow to start** — nvdiffrast JIT-compiles its plugin once;
  later runs load it from cache.
- **Out of memory** — lower the VRAM preset, or set **input resolution** to
  `1/2` (equivalent to `-r 2`) to halve the input resolution.

## License

Non-commercial research use (this repo:
[LICENSE.md](LICENSE.md)). Gaussian Wrapping itself is distributed under the
[Gaussian-Splatting License](https://github.com/toruhashimoto/GaussianWrapping/blob/windows/LICENSE.md)
via the fork the installer checks out. All credit for the method belongs to
the Gaussian Wrapping authors ("From Blobs to Spokes: High-Fidelity Surface
Reconstruction via Oriented Gaussians", Gomez, Guédon, Maruani, Gong,
Ovsjanikov, 2026 — [arXiv:2604.07337](https://arxiv.org/abs/2604.07337)).

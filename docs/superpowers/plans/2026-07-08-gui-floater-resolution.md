# GUI Floater-Removal Toggle + Resolution Preset — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose two existing upstream capabilities as first-class Gradio controls — a background/floater-removal ON/OFF checkbox and a resolution preset — without touching the `GaussianWrapping/` fork.

**Architecture:** Everything routes through `gw.build_run_command` (the single command-builder shared by GUI and CLI). The checkbox maps to the upstream `--no_postprocess` flag (floater removal is already default-on: it keeps the largest connected mesh component). The resolution radio maps to `-r`, with an advanced numeric override retained. No new processing code, no new dependencies, CLI unchanged.

**Tech Stack:** Python 3.11, Gradio 6.19, pytest (dev-only), stdlib `re`.

## Global Constraints

- **No fork edits.** `GaussianWrapping/` is gitignored and out of bounds. Only `gw.py`, `gui.py`, `tests/`, and the two READMEs change.
- **Faithful pass-through preserved.** GUI must build commands only via `gw.build_run_command`; GUI and CLI must not diverge.
- **Backward-compatible defaults.** New `build_run_command(remove_floaters=True)` default must reproduce current behavior exactly (no `--no_postprocess`), so the CLI and existing callers are unaffected.
- **Removal caveat (UI copy, verbatim intent):** connected-component removal only deletes topologically *disconnected* floaters; background connected by thin bridges is not removed.
- **Test runner:** `.venv\Scripts\python.exe -m pytest`. pytest is a dev-only dependency already installed in this working copy's `.venv` (a fresh env needs `pip install pytest`; the proxy may 502 — retry). Baseline before starting: **13 passed**.
- **Branch:** `feat/gui-floater-resolution` (already checked out). Commit after each task with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.

---

### Task 1: `gw.build_run_command` — `remove_floaters` parameter

**Files:**
- Modify: `gw.py:129-150` (`build_run_command`)
- Test: `tests/test_gw.py`

**Interfaces:**
- Produces: `gw.build_run_command(cfg, source, output, quality="fast", vram="16", resolution=None, isosurface=None, extra=(), rasterizer=None, remove_floaters=True)`. When `remove_floaters=False` and `"--no_postprocess"` is not already in `extra`, the command gains a single `--no_postprocess` token. When `True` (default), the command is byte-for-byte identical to today's output.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gw.py` (after `test_build_run_command_user_delaunay_override_not_duplicated`):

```python
def test_build_run_command_remove_floaters_off_adds_no_postprocess():
    cfg = {"env_python": "py", "gw_repo": "gw"}
    on = gw.build_run_command(cfg, "DS", "OUT", "fast", "16")
    assert "--no_postprocess" not in on          # default: removal ON, nothing added
    off = gw.build_run_command(cfg, "DS", "OUT", "fast", "16", remove_floaters=False)
    assert "--no_postprocess" in off


def test_build_run_command_no_postprocess_not_duplicated():
    cfg = {"env_python": "py", "gw_repo": "gw"}
    cmd = gw.build_run_command(cfg, "DS", "OUT", "fast", "16",
                               remove_floaters=False, extra=["--no_postprocess"])
    assert cmd.count("--no_postprocess") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gw.py -k "remove_floaters or no_postprocess" -q`
Expected: FAIL — `TypeError: build_run_command() got an unexpected keyword argument 'remove_floaters'`.

- [ ] **Step 3: Implement the parameter**

In `gw.py`, change the signature and docstring, and add the flag before the `--delaunay_method` block.

Signature (line 129-131) — from:
```python
def build_run_command(cfg, source, output, quality="fast", vram="16",
                      resolution=None, isosurface=None, extra=(),
                      rasterizer=None):
```
to:
```python
def build_run_command(cfg, source, output, quality="fast", vram="16",
                      resolution=None, isosurface=None, extra=(),
                      rasterizer=None, remove_floaters=True):
```

Body (the `extra = list(extra)` block, lines 146-149) — from:
```python
    extra = list(extra)
    if cfg.get("delaunay_method") and "--delaunay_method" not in extra:
        cmd += ["--delaunay_method", cfg["delaunay_method"]]
    cmd += extra
    return cmd
```
to:
```python
    extra = list(extra)
    # remove_floaters is the default upstream behavior (entry script forces
    # --postprocess = keep the largest connected component); disabling it
    # means passing --no_postprocess through to the entry script.
    if not remove_floaters and "--no_postprocess" not in extra:
        cmd += ["--no_postprocess"]
    if cfg.get("delaunay_method") and "--delaunay_method" not in extra:
        cmd += ["--delaunay_method", cfg["delaunay_method"]]
    cmd += extra
    return cmd
```

- [ ] **Step 4: Run the full suite to verify green**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 15 passed (13 baseline + 2 new).

- [ ] **Step 5: Commit**

```bash
git add gw.py tests/test_gw.py
git commit -m "feat: remove_floaters flag on build_run_command (maps to --no_postprocess)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `gui.py` — floater checkbox, resolution preset, rewired command builder

**Files:**
- Modify: `gui.py` (imports; `build_cmd_from_ui` 27-41; `run_pipeline` 54-122; Blocks 163-181)
- Test: `tests/test_gui.py`

**Interfaces:**
- Consumes: `gw.build_run_command(..., remove_floaters=...)` from Task 1.
- Produces:
  - `gui.build_cmd_from_ui(cfg, dataset, output, quality, vram, resolution_preset, resolution_custom, isosurface, remove_floaters, extra_args)` — parses `-r N` out of the preset label (auto label → no `-r`), lets a `resolution_custom > 0` override the preset, and forwards `remove_floaters` (treating `None` as `True`).
  - `gui.run_pipeline(dataset, output, quality, vram, resolution_preset, resolution_custom, isosurface, remove_floaters, extra_args)` — same new field order.
  - Blocks components: `remove_floaters` (Checkbox, default True), `resolution_preset` (Radio, default `"自動 (既定) / auto"`), `resolution_custom` (Number, replaces the old `resolution` Number).

- [ ] **Step 1: Write/adapt the failing tests**

Replace the entire body of `tests/test_gui.py` (below the imports/`CFG`) with:

```python
def test_build_cmd_from_ui_all_optionals_none():
    # regression: untouched Gradio fields arrive as None -> must not raise
    cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", None, None, None, None,
                                None, None, None)
    assert cmd[1].endswith("train_and_extract_gw_ours.py")   # fast default
    assert "-r" not in cmd
    assert "--isosurface_value" not in cmd
    assert "--no_postprocess" not in cmd                     # removal ON by default
    assert cmd[cmd.index("--N_max_gaussians") + 1] == "2500000"  # vram 16 default


def test_build_cmd_from_ui_with_values():
    label = ("high (radegs + フル解像度 + isosurface 0.2) - 最高品質・最も遅い・"
             "VRAM消費大 / maximum quality, slowest")
    cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", label, "96",
                                "自動 (既定) / auto", 0, 0, True,
                                "  --exposure_compensation  ")
    assert cmd[1].endswith("train_and_extract_gw_radegs.py")
    assert cmd[cmd.index("-r") + 1] == "1"                    # from high preset (auto doesn't override)
    assert cmd[cmd.index("--N_max_gaussians") + 1] == "24000000"
    assert cmd[-1] == "--exposure_compensation"


def test_build_cmd_from_ui_zero_isosurface_means_default():
    cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", "fast ...", "16",
                                "自動 (既定) / auto", 0, 0, True, "")
    assert "--isosurface_value" not in cmd


def test_build_cmd_from_ui_resolution_preset_maps_to_r():
    cases = [("自動 (既定) / auto", None),
             ("フル解像度 / full (-r 1)", "1"),
             ("1/2 (-r 2)", "2"),
             ("1/4 (-r 4)", "4")]
    for label, expect in cases:
        cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", "fast", "16", label,
                                    0, 0, True, "")
        if expect is None:
            assert "-r" not in cmd, label
        else:
            assert cmd[cmd.index("-r") + 1] == expect, label


def test_build_cmd_from_ui_custom_r_overrides_preset():
    cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", "fast", "16",
                                "1/2 (-r 2)", 8, 0, True, "")
    assert cmd[cmd.index("-r") + 1] == "8"      # custom 8 wins over preset 2


def test_build_cmd_from_ui_floater_toggle_off_adds_no_postprocess():
    off = gui.build_cmd_from_ui(CFG, "DS", "OUT", "fast", "16",
                                "自動 (既定) / auto", 0, 0, False, "")
    assert "--no_postprocess" in off


def test_run_pipeline_rejects_bad_dataset_early():
    # exercises the new 9-arg run_pipeline signature/order via the early
    # validation path -- no subprocess, no config needed
    gen = gui.run_pipeline("does-not-exist-xyz", "OUT", "fast", "16",
                           "自動 (既定) / auto", 0, 0, True, "")
    states = list(gen)
    assert states, "run_pipeline should yield at least one state"
    assert "エラー" in states[-1][1]   # state tuple = (log, stage, meshes, img1, img2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gui.py -q`
Expected: FAIL — `TypeError: build_cmd_from_ui() takes 8 positional arguments but 11 were given` (and similar for `run_pipeline`).

- [ ] **Step 3a: Add the `re` import**

In `gui.py`, change the import block (lines 8-14) — from:
```python
import glob
import os
import subprocess

import gradio as gr

import gw
```
to:
```python
import glob
import os
import re
import subprocess

import gradio as gr

import gw
```

- [ ] **Step 3b: Rewrite `build_cmd_from_ui`**

Replace `gui.py:27-41` — from:
```python
def build_cmd_from_ui(cfg, dataset, output, quality, vram, resolution,
                      isosurface, extra_args):
    """Build the run command from raw UI values.

    Gradio delivers None for untouched/cleared fields, so every optional
    input is normalized here (regression: AttributeError on
    extra_args.strip() when the advanced accordion was never opened).
    """
    quality_key = (quality or "fast").split()[0]
    extra = extra_args.split() if extra_args and extra_args.strip() else []
    return gw.build_run_command(
        cfg, dataset, output, quality_key, vram or "16",
        resolution=resolution or None,
        isosurface=isosurface if (isosurface is not None and isosurface != 0) else None,
        extra=extra)
```
to:
```python
def build_cmd_from_ui(cfg, dataset, output, quality, vram, resolution_preset,
                      resolution_custom, isosurface, remove_floaters, extra_args):
    """Build the run command from raw UI values.

    Gradio delivers None for untouched/cleared fields, so every optional
    input is normalized here (regression: AttributeError on
    extra_args.strip() when the advanced accordion was never opened).
    """
    quality_key = (quality or "fast").split()[0]
    extra = extra_args.split() if extra_args and extra_args.strip() else []
    # Resolution: the preset label carries its own "-r N" ("auto" has none ->
    # None -> upstream's automatic 1600px cap); a custom -r (>0) overrides it.
    m = re.search(r"-r\s*(\d+)", resolution_preset or "")
    preset_r = int(m.group(1)) if m else None
    effective_r = (int(resolution_custom)
                   if (resolution_custom and int(resolution_custom) > 0)
                   else preset_r)
    remove = True if remove_floaters is None else bool(remove_floaters)
    return gw.build_run_command(
        cfg, dataset, output, quality_key, vram or "16",
        resolution=effective_r,
        isosurface=isosurface if (isosurface is not None and isosurface != 0) else None,
        extra=extra, remove_floaters=remove)
```

- [ ] **Step 3c: Update `run_pipeline` signature and its `build_cmd_from_ui` call**

In `gui.py`, change `run_pipeline`'s signature (line 54) — from:
```python
def run_pipeline(dataset, output, quality, vram, resolution, isosurface, extra_args):
```
to:
```python
def run_pipeline(dataset, output, quality, vram, resolution_preset,
                 resolution_custom, isosurface, remove_floaters, extra_args):
```

And its command-building call (lines 82-83) — from:
```python
    cmd = build_cmd_from_ui(cfg, dataset, output, quality, vram,
                            resolution, isosurface, extra_args)
```
to:
```python
    cmd = build_cmd_from_ui(cfg, dataset, output, quality, vram,
                            resolution_preset, resolution_custom, isosurface,
                            remove_floaters, extra_args)
```

- [ ] **Step 3d: Add the UI components and rewire the click**

In `gui.py`, insert the two new controls after the `vram` radio (currently lines 161-162, ending `label="GPU VRAM (GB) - ガウシアン数上限を自動設定")`). Add immediately below it, at the same indentation (inside `with gr.Column():`):
```python
                remove_floaters = gr.Checkbox(
                    value=True,
                    label="背景/浮遊片を除去（最大の連結成分のみ残す。切断された片のみ対象）"
                          " / Remove background & floaters (keep largest connected part)")
                resolution_preset = gr.Radio(
                    ["自動 (既定) / auto", "フル解像度 / full (-r 1)",
                     "1/2 (-r 2)", "1/4 (-r 4)"],
                    value="自動 (既定) / auto",
                    label="入力解像度 / input resolution")
```

Inside the advanced accordion, replace the old `resolution` Number (line 164) — from:
```python
                    resolution = gr.Number(value=0, label="-r 解像度縮小 (0 = 自動)")
```
to:
```python
                    resolution_custom = gr.Number(
                        value=0, label="カスタム -r（0 = 上のプリセットに従う。"
                                       "target幅や -r 8 用）/ custom -r (0 = follow preset)")
```

Update the click wiring (lines 178-181) — from:
```python
        run_btn.click(run_pipeline,
                      inputs=[dataset, output, quality, vram, resolution,
                              isosurface, extra_args],
                      outputs=[log_box, stage_box, mesh_box, img1, img2])
```
to:
```python
        run_btn.click(run_pipeline,
                      inputs=[dataset, output, quality, vram, resolution_preset,
                              resolution_custom, isosurface, remove_floaters,
                              extra_args],
                      outputs=[log_box, stage_box, mesh_box, img1, img2])
```

- [ ] **Step 4: Run the full suite to verify green**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 19 passed (test_gw.py 12 + test_gui.py 7; test_gui.py went from 3 to 7 tests).

- [ ] **Step 5: Manual smoke — command construction end to end**

Run (verifies the module imports/Blocks build AND the mapping):
```bash
./.venv/Scripts/python.exe -c "import gui; print(gui.build_cmd_from_ui({'env_python':'py','gw_repo':'gw'}, 'DS', 'OUT', 'best (radegs)', '24', '1/2 (-r 2)', 0, 0, False, ''))"
```
Expected: a list containing `train_and_extract_gw_radegs.py`, `-r 2`, and `--no_postprocess`.

- [ ] **Step 6: Commit**

```bash
git add gui.py tests/test_gui.py
git commit -m "feat: GUI floater-removal checkbox + resolution preset

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Documentation (EN + JA READMEs)

**Files:**
- Modify: `README.md` (Use — GUI ~74-81; Troubleshooting ~128-129)
- Modify: `README.ja.md` (使い方 — GUI 69-74; VRAM 不足 line 120)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `README.md` — Use — GUI**

From:
```
choose a quality preset
(`fast`, `best`, or `high` = radegs + full resolution + isosurface 0.2) and your **GPU VRAM** (sets the Gaussian cap),
press **Run**.
```
to:
```
choose a quality preset
(`fast`, `best`, or `high` = radegs + full resolution + isosurface 0.2), your
**GPU VRAM** (sets the Gaussian cap), an **input resolution** (auto / full /
½ / ¼), and whether to **remove background & floaters** (on by default — keeps
only the largest connected part of the mesh; disconnected pieces only),
press **Run**.
```

- [ ] **Step 2: Update `README.md` — Troubleshooting**

From:
```
- **Out of memory** — lower the VRAM preset, or add `-r 2` to halve the input
  resolution.
```
to:
```
- **Out of memory** — lower the VRAM preset, or set **input resolution** to
  `1/2` (equivalent to `-r 2`) to halve the input resolution.
```

- [ ] **Step 3: Update `README.ja.md` — 使い方 — GUI (line 71-72)**

From:
```
指定し、品質プリセット（`fast` / `best` / `high` = radegs+フル解像度+isosurface 0.2）と **GPU VRAM**（ガウシアン数
上限を自動設定）を選んで**実行**。3工程（学習 → メッシュ抽出 → テクスチャ精細化）の
```
to:
```
指定し、品質プリセット（`fast` / `best` / `high` = radegs+フル解像度+isosurface 0.2）、
**GPU VRAM**（ガウシアン数上限を自動設定）、**入力解像度**（自動 / フル / 1/2 / 1/4）、
**背景/浮遊片の除去**（既定ON。メッシュの最大連結成分のみ残す。切断された片のみ対象）を
選んで**実行**。3工程（学習 → メッシュ抽出 → テクスチャ精細化）の
```

- [ ] **Step 4: Update `README.ja.md` — VRAM 不足 (line 120)**

From:
```
- **VRAM 不足** — VRAM プリセットを下げる、または `-r 2` で入力解像度を半分に
```
to:
```
- **VRAM 不足** — VRAM プリセットを下げる、または**入力解像度**を `1/2`（=`-r 2`）にして半分に
```

- [ ] **Step 5: Verify the suite still green (no code change, sanity only)**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 19 passed.

- [ ] **Step 6: Commit**

```bash
git add README.md README.ja.md
git commit -m "docs: document GUI resolution preset + floater-removal toggle

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Do not** run `git add .` — `.venv/` is untracked (not gitignored) and would be committed. Stage the exact files listed per task.
- The happy-path pipeline (real training/extraction) is not unit-tested; after Task 2, a full confidence check is a real GUI launch (`launch_gui.bat`) or the Step-5 command-construction smoke. The `verify` skill can drive this at the end.
- If a fresh environment is used, `pip install pytest` first (proxy may 502 — retry, per the known-flaky-proxy note).

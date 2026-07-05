import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gw


def make_dataset(tmp_path, model="PINHOLE", with_images=True):
    ds = tmp_path / "ds"
    if with_images:
        (ds / "images").mkdir(parents=True)
        (ds / "images" / "0001.jpeg").write_bytes(b"x")
    sparse = ds / "sparse" / "0"
    sparse.mkdir(parents=True)
    (sparse / "cameras.txt").write_text(
        "# Camera list\n1 %s 100 100 90 90 50 50\n" % model, encoding="utf-8")
    (sparse / "images.txt").write_text("", encoding="utf-8")
    (sparse / "points3D.txt").write_text("", encoding="utf-8")
    return str(ds)


def test_check_dataset_ok(tmp_path):
    ok, msgs = gw.check_dataset(make_dataset(tmp_path))
    assert ok, msgs


def test_check_dataset_rejects_radial(tmp_path):
    ok, msgs = gw.check_dataset(make_dataset(tmp_path, model="SIMPLE_RADIAL"))
    assert not ok
    assert any("SIMPLE_RADIAL" in m for m in msgs)


def test_check_dataset_missing_images(tmp_path):
    ok, msgs = gw.check_dataset(make_dataset(tmp_path, with_images=False))
    assert not ok


def test_build_run_command_passthrough_and_presets(tmp_path):
    cfg = {"env_python": r"C:\env\python.exe", "gw_repo": r"C:\gw"}
    cmd = gw.build_run_command(cfg, "DS", "OUT", "radegs", "8",
                               resolution=2, isosurface=0.2,
                               extra=["--exposure_compensation",
                                      "--N_max_gaussians", "999"])
    assert cmd[0] == cfg["env_python"]
    assert cmd[1].endswith("train_and_extract_gw_radegs.py")
    assert cmd[cmd.index("--N_max_gaussians") + 1] == str(gw.VRAM_PRESETS["8"])
    # user extras come AFTER presets -> upstream argparse lets them win
    assert cmd.index("--exposure_compensation") > cmd.index("--N_max_gaussians")
    assert cmd[-1] == "999"
    assert cmd[cmd.index("-r") + 1] == "2"
    assert cmd[cmd.index("--isosurface_value") + 1] == "0.2"


def test_vram_presets_cover_all_choices():
    assert set(gw.VRAM_PRESETS) == {"8", "12", "16", "24", "48", "96"}
    assert gw.VRAM_PRESETS["24"] == 6_000_000  # upstream default
    caps = [gw.VRAM_PRESETS[k] for k in ["8", "12", "16", "24", "48", "96"]]
    assert caps == sorted(caps)  # monotonically increasing with VRAM

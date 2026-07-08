import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gui

CFG = {"env_python": "py", "gw_repo": "gw"}


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

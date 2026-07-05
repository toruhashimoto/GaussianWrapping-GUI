import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gui

CFG = {"env_python": "py", "gw_repo": "gw"}


def test_build_cmd_from_ui_all_optionals_none():
    # regression: untouched Gradio fields arrive as None (advanced accordion
    # never opened) -> must not raise AttributeError
    cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", None, None, None, None, None)
    assert cmd[1].endswith("train_and_extract_gw_ours.py")   # fast default
    assert "-r" not in cmd
    assert "--isosurface_value" not in cmd
    assert cmd[cmd.index("--N_max_gaussians") + 1] == "2500000"  # vram 16 default


def test_build_cmd_from_ui_with_values():
    label = ("high (radegs + フル解像度 + isosurface 0.2) - 最高品質・最も遅い・"
             "VRAM消費大 / maximum quality, slowest")
    cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", label, "96", 0, 0,
                                "  --no_postprocess  ")
    assert cmd[1].endswith("train_and_extract_gw_radegs.py")
    assert cmd[cmd.index("-r") + 1] == "1"                    # from high preset
    assert cmd[cmd.index("--N_max_gaussians") + 1] == "24000000"
    assert cmd[-1] == "--no_postprocess"


def test_build_cmd_from_ui_zero_isosurface_means_default():
    cmd = gui.build_cmd_from_ui(CFG, "DS", "OUT", "fast ...", "16", 0, 0, "")
    assert "--isosurface_value" not in cmd

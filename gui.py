"""GaussianWrapping GUI - local Gradio app.

Beginner flow: pick the COLMAP dataset folder and an output folder, choose a
quality / VRAM preset, press Run. Internally this builds the exact same
command as `gw.py run` (a faithful pass-through to upstream GaussianWrapping
scripts), so the GUI and the CLI cannot diverge.
"""
import glob
import os
import subprocess

import gradio as gr

import gw

HERE = os.path.dirname(os.path.abspath(__file__))
MESH_PATTERNS = ["mesh_*_texture_refined_*.ply", "mesh_*_post.ply", "mesh_*.ply"]


def validate_dataset(path):
    ok, msgs = gw.check_dataset(path)
    head = "✅ このフォルダで実行できます / dataset looks good" if ok else \
           "❌ このフォルダでは実行できません / dataset has problems"
    return head + "\n" + "\n".join(msgs)


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


def _stage_of(line, current):
    if "Step 1/3" in line:
        return "1/3 学習 / training"
    if "Step 2/3" in line:
        return "2/3 メッシュ抽出 / mesh extraction"
    if "Step 3/3" in line:
        return "3/3 テクスチャ精細化 / texture refinement"
    return current


def run_pipeline(dataset, output, quality, vram, resolution, isosurface, extra_args):
    log_lines, stage, meshes, img1, img2 = [], "準備中 / preparing", "", None, None

    def state(extra_line=None):
        if extra_line:
            log_lines.append(extra_line)
        tail = log_lines[-400:]
        return "\n".join(tail), stage, meshes, img1, img2

    ok, msgs = gw.check_dataset(dataset)
    log_lines.extend("  " + m for m in msgs)
    if not ok:
        stage = "エラー / error"
        yield state("[ERROR] データセット検証に失敗しました / dataset validation failed")
        return
    if not output:
        stage = "エラー / error"
        yield state("[ERROR] 出力フォルダを指定してください / output folder is empty")
        return
    os.makedirs(output, exist_ok=True)

    try:
        cfg = gw.load_config()
    except SystemExit as e:
        stage = "エラー / error"
        yield state(str(e))
        return

    cmd = build_cmd_from_ui(cfg, dataset, output, quality, vram,
                            resolution, isosurface, extra_args)
    yield state("[INFO] " + subprocess.list2cmdline(cmd))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            bufsize=1, env=gw.runtime_env(cfg), cwd=cfg["gw_repo"])
    for line in proc.stdout:
        line = line.rstrip("\n")
        stage = _stage_of(line, stage)
        # keep the log readable: drop tqdm carriage-return spam except every ~50th
        if "it/s" in line and len(log_lines) and "it/s" in log_lines[-1]:
            log_lines[-1] = line
            yield state()
            continue
        yield state(line)
    proc.wait()
    if proc.returncode != 0:
        stage = "エラー / error"
        yield state(f"[ERROR] pipeline exited with code {proc.returncode}")
        return

    found = []
    for pat in MESH_PATTERNS:
        found += [p for p in glob.glob(os.path.join(output, pat)) if p not in found]
    meshes = "\n".join(found) if found else "(no mesh found?)"
    stage = "完了 / done"
    if found:
        yield state("[INFO] プレビューを描画中... / rendering preview...")
        pv = subprocess.run([cfg["env_python"], os.path.join(HERE, "render_mesh.py"),
                             "--mesh", found[0], "--out", output],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=gw.runtime_env(cfg))
        if pv.returncode == 0:
            p1 = os.path.join(output, "mesh_preview_view1.png")
            p2 = os.path.join(output, "mesh_preview_view2.png")
            img1 = p1 if os.path.isfile(p1) else None
            img2 = p2 if os.path.isfile(p2) else None
        else:
            yield state("[WARN] preview rendering failed (mesh output itself is fine)")
    yield state("[DONE] 完了しました / all done")


def run_doctor():
    try:
        cfg = gw.load_config()
    except SystemExit as e:
        return str(e)
    r = subprocess.run([cfg["env_python"], os.path.join(HERE, "smoke_test.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=gw.runtime_env(cfg), cwd=HERE)
    return (r.stdout or "") + ("\n" + r.stderr if r.returncode != 0 else "")


with gr.Blocks(title="GaussianWrapping GUI") as demo:
    gr.Markdown(
        "# GaussianWrapping GUI\n"
        "RealityScan などの **COLMAP 出力フォルダ** から、3D Gaussian Splatting ベースの"
        "高品質メッシュを生成します（[Gaussian Wrapping](https://github.com/diego1401/GaussianWrapping) "
        "の Windows 対応版を使用）。 / Generate a high-quality mesh from a COLMAP "
        "dataset via Gaussian Wrapping (Windows fork).")
    with gr.Tab("実行 / Run"):
        with gr.Row():
            with gr.Column():
                dataset = gr.Textbox(label="COLMAP データセットフォルダ / dataset folder "
                                           "(images/ + sparse/ を含む)",
                                     placeholder=r"C:\data\my_scan")
                check_out = gr.Textbox(label="データセット検証 / validation", lines=4,
                                       interactive=False)
                dataset.change(validate_dataset, inputs=dataset, outputs=check_out)
                output = gr.Textbox(label="出力フォルダ / output folder",
                                    placeholder=r"C:\data\my_scan_output")
                quality = gr.Radio(
                    ["fast (ours) - 速い・指標が良い / faster, better metrics",
                     "best (radegs) - 見た目が滑らか / smoother-looking meshes",
                     "high (radegs + フル解像度 + isosurface 0.2) - 最高品質・最も遅い・"
                     "VRAM消費大 / maximum quality, slowest"],
                    value="fast (ours) - 速い・指標が良い / faster, better metrics",
                    label="品質プリセット / quality preset")
                vram = gr.Radio(["8", "12", "16", "24", "48", "96"], value="16",
                                label="GPU VRAM (GB) - ガウシアン数上限を自動設定")
                with gr.Accordion("詳細設定 / advanced", open=False):
                    resolution = gr.Number(value=0, label="-r 解像度縮小 (0 = 自動)")
                    isosurface = gr.Number(value=0, label="--isosurface_value "
                                           "(0 = 既定。細部が欠けるとき 0.2)")
                    extra_args = gr.Textbox(label="追加引数 (上級者向け、そのまま渡されます) / "
                                                  "extra upstream args (verbatim)")
                run_btn = gr.Button("実行 / Run", variant="primary")
            with gr.Column():
                stage_box = gr.Textbox(label="工程 / stage", interactive=False)
                log_box = gr.Textbox(label="ログ / log", lines=22, max_lines=22,
                                     autoscroll=True)
                mesh_box = gr.Textbox(label="出力メッシュ / output meshes", lines=3)
        with gr.Row():
            img1 = gr.Image(label="プレビュー 1 / preview 1", type="filepath")
            img2 = gr.Image(label="プレビュー 2 / preview 2", type="filepath")
        run_btn.click(run_pipeline,
                      inputs=[dataset, output, quality, vram, resolution,
                              isosurface, extra_args],
                      outputs=[log_box, stage_box, mesh_box, img1, img2])
    with gr.Tab("環境診断 / Diagnostics"):
        gr.Markdown("インストール済み環境のスモークテストを実行します（1分弱）。 / "
                    "Runs the environment smoke test (~1 min).")
        doctor_btn = gr.Button("診断を実行 / Run diagnostics")
        doctor_out = gr.Textbox(label="結果 / result", lines=20)
        doctor_btn.click(run_doctor, outputs=doctor_out)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", inbrowser=True)

# GaussianWrapping GUI（日本語版）

![Status: Beta](https://img.shields.io/badge/status-beta-orange)
![Platform: Windows](https://img.shields.io/badge/platform-Windows%2011-blue)
![License: Non--commercial research](https://img.shields.io/badge/license-non--commercial%20research-lightgrey)

**[Gaussian Wrapping](https://github.com/diego1401/GaussianWrapping) の Windows デスクトップアプリ + upstream 忠実な CLI。RealityScan / COLMAP 出力から高品質メッシュを、ワンショットインストーラと「フォルダ2つ選んで実行」の GUI で。**

[English README](README.md)

> [!WARNING]
> **ベータ版です。** end-to-end 検証済みは Windows 11 + RTX 5070 Ti（Blackwell）のみ。
> RTX 30/40 系は同じ手順で動くはずですが（インストーラが GPU アーキテクチャを自動検出）、
> **実機未検証**です。不具合報告は GitHub Issues へお願いします。

ワークフロー: **RealityScan → COLMAP エクスポート → 本 GUI → メッシュ (PLY)**。
生成メッシュを RealityScan の High Detail メッシュと融合する
[rs-gw-mesh-fusion](https://github.com/toruhashimoto/rs-gw-mesh-fusion) と併用できます。

## 前提ソフト（初回のみ、約15分）

| 何 | どこから | 備考 |
|---|---|---|
| NVIDIA ドライバ | https://www.nvidia.com/drivers | RTX 30/40/50 系 (sm_80+) |
| CUDA Toolkit **12.8** | https://developer.nvidia.com/cuda-12-8-0-download-archive | torch cu128 と一致する 12.8 限定（他バージョンと共存可） |
| VS2022 Build Tools | https://visualstudio.microsoft.com/visual-cpp-build-tools/ | 「C++ によるデスクトップ開発」にチェック |
| Miniconda | https://docs.conda.io/en/latest/miniconda.html | Python と CGAL ライブラリの供給元 |

## インストール（全自動、30〜60分）

```bat
git clone https://github.com/toruhashimoto/GaussianWrapping-GUI
cd GaussianWrapping-GUI
install.bat
```

インストーラは前提のチェック（足りないものは入手先を提示）→ conda env 作成 →
torch 2.9.1+cu128 → [Windows fork](https://github.com/toruhashimoto/GaussianWrapping)
（`windows` ブランチ）の clone → 全 CUDA 拡張のビルド（`NVCC_APPEND_FLAGS=-DUSE_CUDA`
等の必須環境変数込み。理由は fork の `WINDOWS.md` 参照）→ CGAL Delaunay 拡張の
ビルド → スモークテスト、まで自動で行います。**失敗後に再実行すると完了済みの
工程はスキップされます。**

## 使い方 — GUI

`launch_gui.bat` をダブルクリック。**COLMAP データセットフォルダ**（`images/` +
`sparse/`。選ぶと自動検証され、問題があれば理由が表示されます）と**出力フォルダ**を
指定し、品質プリセット（`fast/ours` か `best/radegs`）と **GPU VRAM**（ガウシアン数
上限を自動設定）を選んで**実行**。3工程（学習 → メッシュ抽出 → テクスチャ精細化）の
ログが流れ、完了するとメッシュのパスとプレビュー画像が表示されます。
**環境診断**タブからいつでもスモークテストを再実行できます。

RTX 5070 Ti で写真70枚規模なら 1〜1.5 時間程度です。

## 使い方 — CLI（upstream 忠実）

```bat
gw_run.bat run -s C:\data\my_scan -m C:\data\my_scan_out --rasterizer ours --vram 16
```

ラッパーが認識しないフラグは **upstream の `train_and_extract_gw_*.py` にそのまま
渡されます**（upstream の argparse は後勝ちなので、ユーザーのフラグがプリセットを
上書きします）:

```bat
gw_run.bat run -s ... -m ... --vram 16 -r 2 --isosurface_value 0.2 --no_postprocess
gw_run.bat doctor          &REM 環境スモークテスト
gw_run.bat check -s DIR    &REM データセット検証のみ
```

GUI も全く同じコードパスでコマンドを組み立てるため、GUI と CLI の挙動は乖離しません。

## データセット要件

- COLMAP 配置: `images/` + `sparse/0/`（または `sparse/`）に
  `cameras/images/points3D`（`.txt` / `.bin` どちらも可。RealityScan の text 限定
  出力に対応するのが fork のパッチの1つ）
- PINHOLE カメラモデル（歪み補正済み画像）。RealityScan の COLMAP エクスポートは
  この条件を満たします

## サンプルデータ

RealityScan の COLMAP 出力サンプル（写真74枚）を
[最新リリース](https://github.com/toruhashimoto/GaussianWrapping-GUI/releases)
に `Sample_COLMAP.zip` として添付しています。解凍して GUI に指定すれば
すぐ試せます。

## トラブルシューティング

- **インストール中に `error C2872: 'std': あいまいなシンボル`** —
  `NVCC_APPEND_FLAGS=-DUSE_CUDA` なしでビルドしています。手動ビルドせず
  `install.bat` を使ってください
- **tetra_triangulation のビルド失敗** — 追加引数に `--delaunay_method scipy` を
  指定すればパイプラインは動きます（Delaunay 工程が遅くなるだけ）
- **初回実行の起動が遅い** — nvdiffrast が初回のみ JIT コンパイルします（以降はキャッシュ）
- **VRAM 不足** — VRAM プリセットを下げる、または `-r 2` で入力解像度を半分に

## ライセンス

本リポジトリは非商用・研究評価限定（[LICENSE.md](LICENSE.md)）。
Gaussian Wrapping 本体はインストーラが checkout する fork 経由で
[Gaussian-Splatting License](https://github.com/toruhashimoto/GaussianWrapping/blob/windows/LICENSE.md)
で配布されます。手法のクレジットはすべて Gaussian Wrapping の著者
（"From Blobs to Spokes", Gomez et al., 2026 —
[arXiv:2604.07337](https://arxiv.org/abs/2604.07337)）に帰属します。

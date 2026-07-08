# 設計: GUI に「背景/浮遊片除去トグル」と「解像度プリセット」を追加

- 日付: 2026-07-08
- 対象: `GaussianWrapping-GUI`（`gui.py` / `gw.py`）
- ステータス: 承認済み（実装待ち）

## 1. 目的 / Goal

Gradio GUI に、ユーザーが繰り返し必要とする 2 つのコントロールを追加する。

1. **背景/浮遊片除去トグル** — 出力メッシュから対象物とつながっていない浮遊片・背景片を除去する処理の ON/OFF。
2. **解像度プリセット** — 入力解像度のダウンスケール（`-r`）を初心者にも分かるプリセットで選べるようにする。

## 2. 背景 / なぜこの設計か

このプロジェクトの中核方針は **faithful pass-through**（GUI と CLI は同一の `gw.build_run_command` を経由するため乖離しない。未知フラグは upstream に verbatim で渡る）。したがって本設計は **新しい前処理/後処理ロジックを足さず、既に upstream にあるフラグを GUI から露出させるだけ**にとどめる。

fork 調査で確定した事実:

- **浮遊片除去は既に既定で ON。** entry script（`train_and_extract_gw_{ours,radegs}.py`）の `EXTRACT_FLAGS` に `--postprocess` が固定で入っており、`pivot_based_mesh_extraction.py:458` で `post_process_mesh(o3d_mesh, 1)` を呼び、**最大の連結成分 1 つだけ**を残す（`_post.ply` を出力し、テクスチャ精細化はこの `_post.ply` を使う）。
  - ON/OFF は entry script が解釈する `--no_postprocess` で切替可能（**fork 改修不要**）。ただし現状 GUI には露出しておらず、advanced の追加引数欄に打ち込むしかない。
  - 「保持する連結成分の数」(`cluster_to_keep=1`) と 50 三角形の下限は**ハードコード**。これらの調整には fork 改修が必要 → **今回はやらない**（下記スコープ外）。
- **解像度 `-r` は既に露出済み**（advanced の Number 欄）。`utils/camera_utils.py:21-41` により、`-1`（=GUI「自動」）は幅 >1600px のとき 1600px へ自動縮小、`1/2/4/8` は整数分の 1 に縮小、それ以外は target 幅として扱う。意味のある値が少数なのでプリセット化が適する。

### 除去技術の限界（UI で明示する）

連結成分ベースの除去は **トポロジ的に切断された** 浮遊片のみを消す。細い橋でつながった背景は残る（その場合は 3D bbox クロップが必要だが、それはスコープ外）。この限界は UI ラベルに明記する。

## 3. スコープ

### 含む (IN)

- 背景/浮遊片除去 ON/OFF トグル（GUI チェックボックス）
- 解像度プリセット（GUI ラジオ）＋ advanced のカスタム `-r` 上書き欄（既存 Number 欄を転用）
- `gw.build_run_command` / `gui.build_cmd_from_ui` / `gui.run_pipeline` のシグネチャ更新
- テスト更新（`tests/test_gw.py`, `tests/test_gui.py`）
- ドキュメント更新（`README.md`, `README.ja.md`）

### 含まない (OUT) — 理由付き

- **入力画像の前景マスク / matting** — upstream は RGBA アルファチャンネルのみ対応で `masks/` フォルダ読み込みや `--mask` フラグが無い。RealityScan の COLMAP 出力は RGB のみのため、実用にはマスク生成（rembg/SAM 等）という新規前処理と依存追加が必要。faithful-passthrough を壊すため別スペック。
- **3D バウンディングボックスでクロップ** — `bounding_box_*` フラグは `primal_adaptive_meshing_extraction.py`(PAM) 専用で、本線の `pivot_based_mesh_extraction.py` では呼ばれない。別ステージ起動か fork 改修が必要なため別スペック。
- **「保持する連結成分の数 N」「小片の下限しきい値」の調整** — `cluster_to_keep` と 50 三角形下限はハードコード。露出には fork 改修（`--num_cluster` の追加と call site への配線）が必要なため今回は見送り。
- **CLI(`gw.py run`) の新フラグ** — 不要。`-r` も `--no_postprocess` も既に verbatim で通過する。`build_run_command` の新パラメータは既定値が現行動作と一致するため CLI 挙動は不変。

## 4. 詳細設計

### 4.1 機能A — 背景/浮遊片除去トグル

**UI（メイン列、VRAM の下）:**

```python
remove_floaters = gr.Checkbox(
    value=True,
    label="背景/浮遊片を除去（最大の連結成分のみ残す。切断された片のみ対象）/ "
          "Remove background & floaters (keep the largest connected part only)")
```

**コマンドへのマッピング:**

- チェック ON（既定）→ 何も足さない（`--postprocess` は entry script が既定で付与）
- チェック OFF → コマンドに `--no_postprocess` を 1 つ付与

**`gw.build_run_command` の変更:**

```python
def build_run_command(cfg, source, output, quality="fast", vram="16",
                      resolution=None, isosurface=None, extra=(),
                      rasterizer=None, remove_floaters=True):
    ...
    extra = list(extra)
    if not remove_floaters and "--no_postprocess" not in extra:
        cmd += ["--no_postprocess"]
    if cfg.get("delaunay_method") and "--delaunay_method" not in extra:
        cmd += ["--delaunay_method", cfg["delaunay_method"]]
    cmd += extra
    return cmd
```

- `remove_floaters=True`（既定）は現行動作と完全一致 → 既存テスト・CLI に影響なし。
- `extra` に既に `--no_postprocess` があれば重複させない（store_true なので実害は無いが整合のため）。

**出力探索:** `gui.MESH_PATTERNS`（`mesh_*_texture_refined_*.ply`, `mesh_*_post.ply`, `mesh_*.ply`）は post/非post 両方を拾うため **変更不要**。OFF 時は `_post.ply` が出ず `mesh_*_texture_refined_*` または `mesh_*.ply` を拾う。

### 4.2 機能B — 解像度プリセット

**UI（メイン列）:**

```python
resolution_preset = gr.Radio(
    ["自動 (既定) / auto", "フル解像度 / full (-r 1)", "1/2 (-r 2)", "1/4 (-r 4)"],
    value="自動 (既定) / auto",
    label="入力解像度 / input resolution")
```

**advanced のカスタム上書き欄（既存 `resolution` Number 欄を転用・ラベル変更）:**

```python
resolution_custom = gr.Number(
    value=0, label="カスタム -r（0 = 上のプリセットに従う。target幅や -r 8 用）/ "
                   "custom -r (0 = follow preset above)")
```

**マッピング（gui 側で解決）:** ラベル文言の変更に強い**パースルール**で解決する（辞書キーにラベル全文を使わない）:

```python
# ラベルに "-r N" があればその整数、無ければ None（=自動）
m = re.search(r"-r\s*(\d+)", preset_label)
preset_r = int(m.group(1)) if m else None
effective_r = int(custom) if (custom and int(custom) > 0) else preset_r
# build_run_command(resolution=effective_r) に渡す
```

- 「自動 (既定) / auto」→ `None`（`-r` を出さない → upstream `-1` = 幅 >1600 で自動 1600 縮小）
- 「フル … (-r 1)」→ `-r 1`、「1/2 (-r 2)」→ `-r 2`、「1/4 (-r 4)」→ `-r 4`
- カスタム欄が >0 ならプリセットより優先。

**品質プリセット `high`（`-r 1` を強制）との相互作用:**

`build_run_command` は preset flags を先に、resolution を後に積むため **last-wins**。解像度プリセット既定「自動」なら `effective_r=None` で `-r` を出さず、high の `-r 1` がそのまま有効。ユーザーが解像度を明示的に変えたときだけ high を上書きする（既存の isosurface 上書きと同じ挙動で一貫）。

### 4.3 `gui.py` のシグネチャ更新

- `build_cmd_from_ui(cfg, dataset, output, quality, vram, resolution_preset, resolution_custom, isosurface, remove_floaters, extra_args)`
  - Gradio は未操作欄に `None` を渡すため、全 optional を正規化（既存の regression 対策を踏襲）。
  - preset ラベル → キー抽出、custom 正規化、`effective_r` 算出、`remove_floaters` は `bool(...)`（None→True 既定に注意: Checkbox は基本 bool を返すが None 安全に）。
- `run_pipeline(...)` と `run_btn.click(inputs=[...])` を新入力順に合わせて更新。

## 5. テスト計画

`tests/test_gw.py`:

- `remove_floaters=False` → コマンドに `--no_postprocess` が含まれる。
- `remove_floaters=True`（既定）→ 含まれない（現行動作維持）。
- `extra=["--no_postprocess"]` かつ `remove_floaters=False` → `--no_postprocess` は 1 個だけ（重複しない）。
- 解像度: `resolution=None`→`-r` 無し、`1/2/4`→`-r` に正しく反映。
- `high` + `resolution=2` → 最後の `-r` が `2`（last-wins、既存テスト踏襲）。

`tests/test_gui.py`:

- `build_cmd_from_ui` の新シグネチャ・全 optional None で例外なし（regression 継続）。
- 解像度プリセット各ラベル → 期待 `-r`。
- カスタム欄 >0 → プリセットを上書き。
- チェックボックス OFF → `--no_postprocess` 付与、ON → 付与しない。

実行: `.venv\Scripts\python.exe -m pytest`（pytest 未導入なら先に導入）。

## 6. ドキュメント

- `README.md` / `README.ja.md` の「Use — GUI」節に 2 コントロールを追記。
- Troubleshooting の `-r 2`（OOM 対処）記述を、解像度プリセット「1/2」に対応する旨で補足。

## 7. 触るファイル

- `gw.py`（`build_run_command` に `remove_floaters`）
- `gui.py`（UI 追加、`build_cmd_from_ui` / `run_pipeline` / `click` 更新、Number 欄ラベル変更）
- `tests/test_gw.py`, `tests/test_gui.py`
- `README.md`, `README.ja.md`
- fork（`GaussianWrapping/`）は **触らない**。

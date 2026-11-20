# photo-mole-game v1.3.0 Release Notes

> This is the English version. 中文版见同级目录 `RELEASE_NOTES_v1.3.0.md`.

- Release date: 2026-11-19
- Previous version: v1.2.0
- Author: JaJa
- Theme: **cutouts must not eat the subject, cartoons must look like the actual person** — the two failure modes found in real runs (white shirts turning transparent, hair and collars keyed out as background; cartoon faces degrading into a generic anime face) are now enforced by scripts and hard gates.

---

## 1. Cutout hardening (requirement 1)

### 1.1 New / enhanced capabilities (`scripts/cutout.py`)

| Capability | Flags | What it does |
| --- | --- | --- |
| Pre-cutout analysis | `--analyze` / `--analyze-report <json>` | Measures background uniformity, subject ratio and colour distance, then recommends `--tol` / `--bg-hex` instead of guessing |
| Subject protection (on by default) | disable with `--no-protect`, tune with `--protect-radius <n>` | Chroma-key output is **cross-checked** against the GrabCut foreground; regions punched out inside the subject are filled back. People, clothing and accessories may not be keyed out as background |
| Post-cutout verification | `--verify --report cutout.report.json` | Nine metrics against an **independent subject baseline** (not self-referential mask checks): `keep_ratio / iou / hole_rate / edge_cut_ratio / comp2_ratio / dent_ratio / dent_area_ratio / fg_ratio / edge_color_diff` |
| Comparison sheets | `--compare --compare-dir <dir>` / `--compare-only` | Side-by-side original vs cutout, plus a contact sheet, so a human can judge in one look |
| Adaptive background | `--chroma auto` | Reads `bg.hex` from `manifest.json` instead of hand-typing the colour |

### 1.2 Verdict thresholds (script constants, not just documentation)

- `dent_ratio > 0.50` **and** `dent_area_ratio > 1%` → FAIL
- `dent_ratio > 0.65` → FAIL
- Soft metric above `T_DENT_WARN = 0.48` → WARN
- On FAIL, `cutout.py` exits with **code 2** and lists the keys to redo; the pipeline cannot continue to build

### 1.3 Real interception evidence

| Asset | Result | Symptom |
| --- | --- | --- |
| `01_smug.png` | PASS | Subject intact, hair and clothing edges clean |
| `05_angry.png` | **FAIL** (exit 2) | Large chunks of hair missing on both sides, collar keyed out on the left shoulder — exactly the "half the person is gone" case this version blocks |

### 1.4 SKILL.md rewritten in sync

- Red lines grow from 4 to **6**; the new #5 forbids swallowing the subject, clothing or accessories and requires analysis before and comparison after cutout, with the typical failures spelled out (transparent white shirt, missing glasses, purple fringe around hair, vanished earrings).
- Stage B is now four steps: **analyse → fix parameters → cut out → compare**, and "no report, no build".

---

## 2. Cartoon identity hardening (requirement 2)

### 2.1 New `scripts/identity.py`

| Capability | Flags | What it does |
| --- | --- | --- |
| Feature skeleton | `--template --out <json>` | 22-key template: `face_shape / skin_tone / hair_length / hair_parting / hair_color / bangs / hair_texture / eyebrows / eyes / glasses / nose / mouth / ears / marks / accessories / clothing / age_feel / distinctive` and more |
| Completeness check | `--validate --features <json>` | Lists every missing field (all 11 missing ones reported in the real test); a vague one-line description is no longer enough to start generating |
| Prompt export | `--emit --features <json>` | Emits an English `desc`, **11 identity-lock positive terms**, **9 negative terms** (`different person / generic anime face / wrong hairstyle / missing glasses / changed face shape …`) and a Chinese summary of the features |
| Similarity scoring | `--compare-sheet --photo <original> --cartoon <cartoon>` | Produces an original-vs-cartoon comparison sheet and a similarity score, which becomes the value used by the identity gate |

### 2.2 Pipeline integration

- **Stage A0 (new)**: analyse the real person's facial features field by field before any generation, producing `features.json` plus a Chinese summary for the user to confirm.
- `gen_expressions.py --features <json>`: loads the features and writes both the `desc` and the identity-lock terms into every expression prompt, with negatives appended automatically.
- `gate.py` gains `--identity-features / --identity-score / --identity-compare`; `build_game.py` adds an `identity` gate: **score < 65 refuses to build**, 65–79 → adjust features and regenerate, ≥ 80 → hand to the user for confirmation.

---

## 3. Installer (requirement 3)

- Single-file exe: `photo-mole-game-installer.exe` (PyInstaller `--onefile --windowed`, 19-file / 408,571-byte payload embedded, no Python needed on the target machine).
- Supported agents 28 → **31**:

| Display name | agent key | Default target |
| --- | --- | --- |
| DeepSeek Harness | `deepseek-harness` | `~/.dsh/skills/photo-mole-game` (also detects a project-local `.dsh`) |
| Kimi | `kimi` | `~/.kimi/skills/photo-mole-game` |
| Doubao Work (豆包工作) | `doubao` | Manual import: exports to `~/photo-mole-game-import` (skill folder + skill zip + import guide) |

- Doubao keeps its skills inside an app-managed workspace (`%LOCALAPPDATA%/Doubao/User Data/Default/.doubao/agent_mode/workspace/.skills`), so the installer exports instead of writing there.

### 3.1 Acceptance tests (all against the final exe)

| # | Item | Result | Observed |
| --- | --- | --- | --- |
| 1 | exe build | pass | 10,436,783 B, SHA256 `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A` |
| 2 | `--cli --list` | pass | 31/31 entries, 7 detected / 24 not detected, WorkBuddy shown as `v1.3.0`, exit 0 |
| 3 | Real install (workbuddy → temp dir) | pass | 19 files / 408,571 B, `version: 1.3.0`, no `__pycache__` |
| 4 | Idempotent re-run | pass | `[UNCHANGED]`, no `.bak-*` created |
| 5 | Overwrite after tampering + backup | pass | `[UPDATE]`, created `photo-mole-game.bak-20261119-175450` |
| 6 | Doubao manual-import branch | pass | Exported skill folder + `photo-mole-game_v1.3.0.zip` + import guide |
| 7 | GUI launch | pass | Title `photo-mole-game 技能一键安装器 v1.3.0`, window in 1.07 s |
| 8 | Protected system directory refused | pass | `--dest C:/Program Files/pmfail` → `[ERR]`, exit 1 |
| 9 | Invalid agent key refused | pass | `--agents no-such` → `[ERR]`, exit 1 |

---

## 4. Working with a local graphics model (end-to-end local image generation)

The skill is **model-agnostic**: image generation only talks HTTP, so a local offline engine and a hosted model are interchangeable. Below are the three wiring options, the parameters that must line up, and the three gates that still apply after the model has drawn something.

### 4.1 Three integration paths

| Path | How | When |
| --- | --- | --- |
| **A. Fully automatic local batch (recommended)** | Start `sd-server` (stable-diffusion.cpp core, A1111-compatible API) and pass `--endpoint http://127.0.0.1:8790`; all 11 expressions are generated in one command | Engine already running; want the whole set from one command |
| **B. Per-image via MCP** | Run `gen_expressions.py --manifest-only` to export `raw/manifest.json` (prompt / negative / seed per expression), then have the agent call `locmodel-image`'s `redraw_image(init_image=<photo>, prompt=…, negative_prompt=…, strength=0.66, seed=…)` and save as `raw/<key>.png` | Engine is managed by MCP, model priority is automatic, or you switch models often |
| **C. Hosted model fallback** | Feed the same manifest to an online img2img / photo-to-cartoon model, return files as `raw/<key>.png` | No local GPU or no local engine |

### 4.2 Engine readiness checks (MCP path, do these first)

| Tool | Purpose |
| --- | --- |
| `locmodel_status` | Port, loaded model, engine defaults, VRAM and size policy |
| `engine_discover` | LocModel may pick a new port after a restart — rediscover |
| `engine_doctor` | Self-check on failure: Python, engine reachability, model, VRAM vendor, output dir writability, helper tools |
| `list_models` / `list_edit_models` / `load_model` | List models and switch, waiting until the engine confirms the load |

Models seen in practice: **flux2-klein (flux.2 klein 4B)** and **z_image_turbo (z_image_turbo-Q4_K)**, both capable of img2img; lower quantization = less VRAM. Reference speed: roughly 20–60 s per 1024×1024 image on a mid-range GPU.

### 4.3 Parameters that must line up

| Flag | Expressions (`gen_expressions.py`) | Prize image (`gen_prize.py`) | Notes |
| --- | --- | --- | --- |
| `--endpoint` | `http://127.0.0.1:8790` | same | Left empty ⇒ manifest only; it will never silently switch to a hosted model |
| `--strength` | `0.66` (typical 0.55–0.75) | `0.80` (0.78–0.88 for half-body → full-body) | Too low ⇒ nothing changes; too high ⇒ no longer the same person |
| `--steps` | `20` | `24` | Turbo/distilled models can go lower |
| `--sampler` | `euler` | `euler` | Match the engine side |
| `--cfg` | `7.0` | `7.0` | Distilled models: follow the model card |
| `--width` / `--height` | `832 × 1024` | `832 × 1216` | Multiples of 8 |
| `--seed` | `20261112` (per image = seed + idx×13) | `20261118` | Fixed seeds keep runs reproducible |
| `--bg` | `magenta` (#FF00FF) | n/a | One of magenta / green / blue / white |

Prize images also use `--init assets/normal.png` (extend the locked-in expression character to a full body), `--poses 3`, `--per-diff normal,hard,hell`.

### 4.4 img2img input rules (ignoring these always costs score)

1. **init_image must be the person themselves** — the user's photo for expressions, `assets/normal.png` for prize images. Starting from someone else's photo or a recompressed copy cannot be rescued by identity-lock terms.
2. **Always pass `--features`** — `features.json` injects the 22 facial features into `desc`, the identity-lock positives and the negatives. Without it you get a generic anime face, `identity.py` scores below 65 almost every time, and `build_game.py` refuses to build.
3. **Pure flat background only** — the background clause is already baked into the prompt (`{bg} background (#HEX), completely uniform fill, no gradient, no vignette, no shadow, no props`), and the hex value lands in `raw/manifest.json` → `bg.hex` for stage B (`--chroma auto`).
4. **Never hand-edit the exported prompts** — especially on the MCP / hosted paths; dropping the background clause or the negatives breaks both cutout and identity scoring.

### 4.5 Division of labour (the model only draws)

| Stage | Owner | Network |
| --- | --- | --- |
| Expression / prize generation | Local diffusion model (or hosted model) | Local path is fully offline |
| Cutout, canvas normalisation | `cutout.py` (chroma key + GrabCut + connected components, local CPU) | No |
| Identity scoring, comparison sheets | `identity.py` (local image metrics) | No |
| Gates, build, regression | `gate.py` / `build_game.py` / `verify_game.py` | No |

The skill **never writes engine configuration**: it does not touch LocModel's `config.json`; model loading and VRAM strategy stay on the engine / MCP side, and parameters travel in the per-job HTTP payload.

### 4.6 Three gates after the model draws (any one fails ⇒ no build)

1. **Contact-sheet gate**: `make_sheet.py` builds the sheet and runs `bgcheck` (flat-background check); a sheet flagged FAIL may not be presented as "approvable".
2. **Identity gate**: `identity.py --compare-sheet` produces the original-vs-cartoon sheet and score — ≥ 80 may go to the user, 65–79 means adjust features and regenerate, < 65 and `build_game.py` refuses to build.
3. **Cutout gate**: `cutout.py --verify` writes `cutout.report.json`; any FAIL among the nine metrics (including the `dent_ratio` thresholds) exits with code 2 and stops the pipeline.

### 4.7 Quick self-check

```bash
# Engine side
locmodel_status            # or simply check http://127.0.0.1:8790
engine_doctor              # run this first when generation fails

# Skill side
python scripts/identity.py --template --out features.json     # 1. feature skeleton
python scripts/gen_expressions.py --photo me.jpg --out raw/ \
    --endpoint http://127.0.0.1:8790 --features features.json \
    --strength 0.66 --two-stage                               # 2. local batch generation
python scripts/make_sheet.py --in raw --out raw/sheet.jpg --cols 4   # 3. contact sheet for the user
python scripts/identity.py --compare-sheet --photo me.jpg \
    --cartoon assets/normal.png --features features.json \
    --out identity.compare.jpg --score-out identity.score.json       # 4. identity score
python scripts/cutout.py --in raw/ --analyze                  # 5. pre-cutout analysis
python scripts/cutout.py --in raw/ --out assets/ --normalize \
    --chroma auto --tol <recommended> --verify --compare      # 6. cutout + report
```

---

## 5. Release assets

| File | Bytes | SHA256 |
| --- | --- | --- |
| `photo-mole-game-installer.exe` | 10,436,783 | `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A` |
| `photo-mole-game_v1.3.0.zip` | 155,111 | `4A63F892FB07F2D7239DF1274D7BF7465D779F80E169655060249F973858035E` |
| `CHECKSUMS-v1.3.0.txt` | see file | Per-file hashes for all 19 package files plus deliverables |
| `RELEASE_NOTES_v1.3.0.md` (zh) / `.en.md` | these files | — |

Skill package: 19 files / 408,571 B with per-file sha256 in `manifest.json`; the zip root is `photo-mole-game/`, excludes `__pycache__` / `*.pyc`, and matches the source tree byte for byte.

---

## 6. Upgrade and rollback

- Upgrade: double-click the exe, tick the target agents, install (the previous install is backed up as `photo-mole-game.bak-<timestamp>`); or unzip and copy `photo-mole-game/` into `<agent>/skills/`.
- Rollback: delete the installed folder and rename the backup back, or fetch the v1.2.0 assets.
- Verify: `Get-FileHash <file> -Algorithm SHA256` against section 5 and `CHECKSUMS-v1.3.0.txt`.

## 7. Known limitations

- Cutout verdicts are heuristic: very light hair on white, semi-transparent clothing and similar extreme material may still need a human look at the comparison sheet.
- The cartoon similarity score is an image-metric aid; the final "does it look like me" judgement stays with the user.
- Doubao Work is not written into directly — one manual import per the export guide.
- Local generation speed depends heavily on GPU and quantization; this release does not publish a unified benchmark. For large batches, tune parameters on a single image with `--only` first.

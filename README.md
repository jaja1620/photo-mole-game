# photo-mole-game · Photo → Whack-a-Mole Game Skill

**English** | [简体中文](README.zh-CN.md)

An Agent Skill that turns **one photo** into an **offline, single-file whack-a-mole HTML game** — the mole popping out of the holes is the person in the photo, re-imagined as a cartoon avatar that laughs, winces and begs for mercy.

Built and regression-tested end-to-end on a real project (`敲谈姐儿 v1.4.0`), then frozen into a reusable pipeline. Works with any agent that supports the open [Agent Skills](https://agentskills.io) `SKILL.md` format: Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, CodeBuddy, WorkBuddy, Trae, Qoder, Cline, Roo Code, Windsurf, Kiro and ~20 more.

- **Version**: 1.3.0 · **Author**: JaJa · **License**: MIT
- **Output**: pure front-end, zero dependency, zero network, double-click to play (desktop & mobile browsers)
- **Runtime deps**: Python 3.11 + `pillow numpy opencv-python` (verification stage additionally needs Playwright + local Edge)
- **Image generation**: model-agnostic — any local `sd-server` / MCP-hosted engine or a hosted model, see [Working with a local graphics model](#working-with-a-local-graphics-model)

---

## What it does

```
photo ──► identity analysis (22 facial features, locked-in prompts)
      ──► cartoon avatar (11 expressions, flat chroma background)
      ──► identity score vs. the original photo (gate ≥ 80 to ship)
      ──► cutout + canvas normalisation (analyse → cut → verify → compare)
      ──► prize image (uploaded / AI-generated / locally composed)
      ──► config.json (theme, difficulties, rewards, easter eggs)
      ──► build ──► folder build + single-file HTML
      ──► headless regression verification (Playwright + Edge CDP)
```

| Stage | Script | Responsibility |
| --- | --- | --- |
| Gate | `scripts/gate.py` | Records user confirmations into `gate.json` (photo / sheet / prize / identity); `--show` lists what is still missing |
| A0 | `scripts/identity.py` | 22-key facial-feature template → English `desc`, identity-lock positives/negatives, original-vs-cartoon score |
| A | `scripts/gen_expressions.py` | Batch-generates 11 expression raw images on a pure chroma background, or exports a prompt manifest for MCP / hosted models |
| A' | `scripts/make_sheet.py` | Builds the contact sheet **and runs a background check** (`bgcheck.json`) before anything is shown to the user |
| B | `scripts/cutout.py` | `--analyze` → parameters → chroma key + GrabCut + connected components with subject protection → `--verify` report → `--compare` sheets |
| P | `scripts/gen_prize.py` | Prize image: user upload, AI full-body generation, or local `compose` layouts (card / circle / badge) |
| C–D | `scripts/build_game.py` | Validates the gate and the cutout report, then injects `__MOLE_CONFIG__` into the template and emits both build flavours |
| E | `scripts/verify_game.py` | Headless regression over both builds via Playwright + Chrome DevTools Protocol against local Edge |

`assets/game_template.html` holds every variable as a `__MOLE_CONFIG__` placeholder — **you change the config, never the template**.

### The game itself

- 4 difficulty tiers (轻松 / 普通 / 困难 / 地狱) with configurable level counts and lives — the reference build runs 9 / 9 / 12 / 15 levels and 15 / 10 / 8 / 6 lives
- 11-expression avatar: different faces for popping up (mockery), being hit (pain), and escaping
- Gold / colour eggs grant extra lives; when lives are capped the reward converts into bonus score
- Obstacles: black bird, bomb, nuke (harder tiers only)
- Clearing a tier opens an easter-egg page with confetti and a "claim your prize" image
- Procedural WebAudio SFX, no external assets, fully responsive

### Six hard red lines (enforced by scripts, not by good intentions)

`build_game.py` refuses to build unless `gate.json` says every gate was passed:

1. **The photo source must be chosen by the user** — upload / local path / "pick a few from my library". The skill must stop and wait; it may never go hunting through the photo library on its own.
2. **The expression contact sheet must be shown and confirmed, on a pure flat background** — only `magenta / green / blue / white` chroma backgrounds are allowed. A sheet flagged `FAIL` by the background check may not be presented as "approvable".
3. **Prize image: source and coverage must be asked first** — upload / auto-generate / local compose, plus "one shared image" vs "one per difficulty".
4. **Every difficulty except 轻松 (easy) must ship its own prize image** — `easy` has none by design; `normal / hard / hell` each need a finalised one or the build fails.
5. **Cutout must not eat the subject, clothing or accessories** — analyse parameters before cutting, and compare afterwards. White shirts turning transparent, glasses vanishing, purple fringing around hair, missing earrings are all explicit failures.
6. **The cartoon must be derived from a real feature analysis and pass the similarity score** — no `features.json`, no generation; a score below 80 goes back for another round, below 65 the build is refused.

---

## Working with a local graphics model

The skill never bundles a model and never talks to a vendor API directly: generation is a plain HTTP call, so **any** local engine (stable-diffusion.cpp / `sd-server`, A1111-compatible API) or a hosted model can drive it.

### Three wiring options

| Path | How | When |
| --- | --- | --- |
| **A. Local batch (recommended)** | Start `sd-server` and pass `--endpoint http://127.0.0.1:8790`; the 11 expressions are produced in one command | The engine is already running |
| **B. Through MCP** | `gen_expressions.py --manifest-only` exports `raw/manifest.json`; the agent then calls `locmodel-image` → `redraw_image(init_image=<photo>, prompt=…, negative_prompt=…, strength=0.66, seed=…)` per expression | The engine is managed by MCP, or you want model priority handled for you |
| **C. Hosted model** | Hand the same manifest to an online img2img model, save as `raw/<key>.png` | No local GPU |

### Engine checks (MCP path)

`locmodel_status` (port / loaded model / VRAM) → `engine_discover` (after a restart) → `engine_doctor` (self-check on failure) → `list_models` / `list_edit_models` / `load_model` (switch and wait for confirmation). Models that work well here: **flux2-klein (flux.2 klein 4B)** and **z_image_turbo (z_image_turbo-Q4_K)** — both do img2img. Reference speed: ~20–60 s per 1024×1024 frame on a mid-range GPU.

### Parameters to line up

| Flag | Expressions | Prize image | Notes |
| --- | --- | --- | --- |
| `--strength` | `0.66` (0.55–0.75) | `0.80` (0.78–0.88) | Low keeps the original, high drifts away from the person |
| `--steps` / `--sampler` / `--cfg` | `20` / `euler` / `7.0` | `24` / `euler` / `7.0` | Distilled models: follow the model card |
| `--width` × `--height` | `832 × 1024` | `832 × 1216` | Multiples of 8 |
| `--seed` | `20261112` (+ idx×13) | `20261118` | Reproducible batches |
| `--bg` | `magenta` / `green` / `blue` / `white` | n/a | Flat colour only, written to `manifest.json` → `bg.hex` |

### Rules that decide whether the result survives the gates

- **init_image must be the person**: the user's photo for expressions, `assets/normal.png` for prize images.
- **Always pass `--features features.json`**: it rewrites the `desc`, adds 11 identity-lock terms and 9 negatives. Without it you get a generic anime face and the identity score drops under 65, which blocks the build.
- **Never hand-edit exported prompts** — the flat-background clause and the negatives are load-bearing for both cutout and identity scoring.
- **The model only draws**: cutout, identity scoring, gating, building and regression all run locally on CPU and never call out. The skill never edits the engine's own config; parameters travel in the per-job payload.

Full details, including the post-generation gate chain and self-check commands, are in [RELEASE_NOTES_v1.3.0.en.md](RELEASE_NOTES_v1.3.0.en.md).

---

## Install

### Option A — One-click installer (GUI, recommended)

Download `photo-mole-game-installer.exe` from [Releases](https://github.com/jaja1620/photo-mole-game/releases/latest) (10.4 MB, single file, no Python required on the target machine).

| Step | What happens |
| --- | --- |
| 1 | Double-click the exe — a GUI opens (Tkinter, Chinese UI) |
| 2 | **Auto-detect**: the installer scans 31 agent config directories and pre-ticks every agent it finds; the rest show as "not detected" |
| 3 | Every row shows its target directory; click **浏览…** on a row to override that path |
| 4 | **一键安装到勾选项** installs the bundled skill (v1.3.0, 19 files / 408,571 B) into `<agent-skills-dir>/photo-mole-game` |
| 5 | No agent detected, or you want a private location? Use **选择自定义目录安装…** and pick any directory |

Behaviour details that matter:

- **Idempotent** — if the target already matches the payload byte-for-byte, it reports `[UNCHANGED]` and writes nothing
- **Backup before overwrite** (on by default) — the previous install is renamed to `photo-mole-game.bak-YYYYMMDD-HHMMSS`
- **Result log** — each line is `[OK]` / `[UPDATE]` / `[UNCHANGED]` / `[SKIP]` / `[ERR]` plus the path, with a summary
- **System directories are refused** — installing into `C:\Windows`, `C:\Program Files`, etc. fails with an explicit error
- **Doubao Work** is exported for manual import (`~/photo-mole-game-import`) because the app manages its own skills workspace

CLI mode (same exe, useful for scripting or silent deployment):

```bat
photo-mole-game-installer.exe --cli --list
photo-mole-game-installer.exe --cli --install --all --yes
photo-mole-game-installer.exe --cli --install --agents claude-code,cursor --dest D:\my-skills
```

A log is always written to `%TEMP%\photo-mole-installer.log`.

### Option B — Manual install (no exe)

A skill is just a directory containing `SKILL.md`. Copy the `skill/` folder of this repo into your agent's skills directory, keeping the `photo-mole-game/` level:

```powershell
# Windows, PowerShell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.workbuddy\skills" | Out-Null
Copy-Item .\skill "$env:USERPROFILE\.workbuddy\skills\photo-mole-game" -Recurse
```

```bash
# macOS / Linux
mkdir -p ~/.workbuddy/skills
cp -r skill ~/.workbuddy/skills/photo-mole-game
```

There is also a bundled `skill/install.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target "$env:USERPROFILE\.workbuddy\skills"
#   -Force   overwrite without asking (still backs up first)
#   -DryRun  show what would happen, touch nothing
```

Or unzip `photo-mole-game_v1.3.0.zip` (from Releases) straight into the skills directory — the archive root is already `photo-mole-game/`.

Restart (or refresh the skill panel of) your agent — the skill appears as **照片打地鼠游戏生成器 / Photo Whack-a-Mole Game**.

### Where each agent looks (user-level skills directory)

| Agent | Directory |
| --- | --- |
| Claude Code | `~/.claude/skills` |
| Codex | `~/.codex/skills` |
| Cursor | `~/.cursor/skills` |
| Gemini CLI | `~/.gemini/skills` |
| Antigravity | `~/.gemini/antigravity/skills` |
| GitHub Copilot | `~/.copilot/skills` |
| CodeBuddy | `~/.codebuddy/skills` |
| WorkBuddy | `~/.workbuddy/skills` |
| Trae | `~/.trae/skills` |
| Qoder | `~/.qoder/skills` |
| Cline | `~/.cline/skills` |
| Roo Code | `~/.roo/skills` |
| Windsurf | `~/.codeium/windsurf/skills` |
| Kiro CLI | `~/.kiro/skills` |
| Kilo Code | `~/.kilocode/skills` |
| OpenCode | `~/.config/opencode/skills` |
| OpenHands | `~/.openhands/skills` |
| Goose | `~/.config/goose/skills` |
| Amp | `~/.config/agents/skills` |
| Qwen Code | `~/.qwen/skills` |
| Command Code | `~/.commandcode/skills` |
| Droid | `~/.factory/skills` |
| Clawdbot | `~/.clawdbot/skills` |
| MCPJam | `~/.mcpjam/skills` |
| Neovate | `~/.neovate/skills` |
| Pi | `~/.pi/agent/skills` |
| Zencoder | `~/.zencoder/skills` |
| DeepSeek Harness | `~/.dsh/skills` |
| Kimi | `~/.kimi/skills` |
| Doubao Work (manual import) | `~/photo-mole-game-import` |
| Any agent (portable) | `~/.agents/skills` |

The one-click installer ships exactly this table (31 entries) and detects an agent by the presence of its config directory.

### Verify the install

```bash
pip install pillow numpy opencv-python
python ~/.workbuddy/skills/photo-mole-game/scripts/gate.py --file /tmp/g.json --show
python ~/.workbuddy/skills/photo-mole-game/scripts/build_game.py --help
```

If both commands run, the package is complete. `SKILL.md` frontmatter `version` and `manifest.json` `version` should both read `1.3.0`.

---

## Using it

Just ask your agent, in plain language:

> "用我这张照片做个打地鼠小游戏" / "Make a whack-a-mole game out of this photo"

The agent then:

1. asks **where the photo comes from** (upload / path / pick from library) and waits;
2. analyses the person's facial features into `features.json` (stage A0);
3. generates 11 expressions on a flat chroma background, scores the cartoon against the photo, assembles a contact sheet and asks **all pass / redo all / redo these**;
4. asks **where the prize image comes from** and whether all difficulties share one;
5. runs the cutout with analysis and verification, and stops if the report contains any FAIL;
6. writes `config.json` (title, tiers, levels, lives, rewards, easter-egg copy);
7. builds the folder version and the single-file HTML, then runs the headless regression;
8. hands you a double-clickable `.html`.

Anything goes wrong, real-world traps are catalogued in `skill/references/pitfalls.md`.

---

## Repository layout

```
skill/                 the skill package itself (v1.3.0, 19 files)
  SKILL.md             pipeline spec + the six red lines
  scripts/             gate / identity / expressions / sheet / cutout / prize / build / verify
  assets/              game_template.html (all variables are __MOLE_CONFIG__)
  references/          config schema, expression list, pitfalls
  examples/            config.qiaotan.json, config.minimal.json
  install.ps1          PowerShell installer (backup + verify)
  manifest.json        per-file sha256
installer/             source of the GUI one-click installer (v1.3.0, 31 agents)
  photo_mole_installer.py    Tkinter GUI + CLI, single file
  build.ps1 / build.bat      reproducible PyInstaller build (payload = payload/photo-mole-game)
  photo-mole-game-installer.spec   portable spec, same payload resolution
CHECKSUMS.txt          sha256 of the v1.3.0 release assets
RELEASE_NOTES_v1.3.0.md / .en.md   bilingual release notes
```

## Release assets

| Asset | Size | SHA256 |
| --- | --- | --- |
| `photo-mole-game-installer.exe` | 10,436,783 B | `52248D15B1E7B92301103E4E50F32904B9B2414E9B154351BD5126CE32EFD82A` |
| `photo-mole-game_v1.3.0.zip` | 155,111 B | `4A63F892FB07F2D7239DF1274D7BF7465D779F80E169655060249F973858035E` |
| `CHECKSUMS-v1.3.0.txt` | 2,839 B | — |
| `RELEASE_NOTES_v1.3.0.md` (中文) / `.en.md` (English) | — | — |

## Changelog

| Version | Highlights |
| --- | --- |
| 1.3.0 | Cutout hardening (`--analyze` parameter guidance, subject protection on by default, `--verify` nine-metric report, `--compare` sheets) + identity hardening (new `identity.py` 22-key feature template, `--features` identity lock, identity gate in `gate.py` / `build_game.py`). Red lines 4 → 6. Installer covers 31 agents |
| 1.2.0 | Pure-colour background rule + background check before showing the sheet; prize coverage per difficulty; `gen_prize.py --mode compose` local layout synthesis; `--chroma auto` cutout reading `manifest.json` |
| 1.1.0 | Gate hard-fail: `build_game.py` refuses to build without `gate.json`; contact-sheet confirmation loop; prize image source question |
| 1.0.0 | First pipeline: expressions → cutout → config → build → headless verify |

## License

MIT. Author: **JaJa**.

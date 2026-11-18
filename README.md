# photo-mole-game · Photo → Whack-a-Mole Game Skill

**English** | [简体中文](README.zh-CN.md)

An Agent Skill that turns **one photo** into an **offline, single-file whack-a-mole HTML game** — the mole popping out of the holes is the person in the photo, re-imagined as a cartoon avatar that laughs, winces and begs for mercy.

Built and regression-tested end-to-end on a real project (`敲谈姐儿 v1.4.0`), then frozen into a reusable pipeline. Works with any agent that supports the open [Agent Skills](https://agentskills.io) `SKILL.md` format: Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, CodeBuddy, WorkBuddy, Trae, Qoder, Cline, Roo Code, Windsurf, Kiro and ~15 more.

- **Version**: 1.2.0 · **Author**: JaJa · **License**: MIT
- **Output**: pure front-end, zero dependency, zero network, double-click to play (desktop & mobile browsers)
- **Runtime deps**: Python 3.11 + `pillow numpy opencv-python` (verification stage additionally needs Playwright + local Edge)

---

## What it does

```
photo ──► cartoon avatar (11 expressions, flat chroma background)
      ──► cutout + canvas normalisation (transparent PNG, head/feet aligned)
      ──► prize image (uploaded / AI-generated / locally composed)
      ──► config.json (theme, difficulties, rewards, easter eggs)
      ──► build ──► folder build + single-file HTML
      ──► headless regression verification (Playwright + Edge CDP)
```

| Stage | Script | Responsibility |
| --- | --- | --- |
| Gate | `scripts/gate.py` | Records user confirmations into `gate.json`; `--show` lists what is still missing |
| A | `scripts/gen_expressions.py` | Batch-generates 11 expression raw images on a pure chroma background, or exports a prompt manifest for MCP / online models |
| A' | `scripts/make_sheet.py` | Builds the contact sheet **and runs a background check** (`bgcheck.json`) before anything is shown to the user |
| B | `scripts/cutout.py` | Chroma-key first, then GrabCut, flood-fill and connected-component cleanup; normalises every expression to one canvas |
| P | `scripts/gen_prize.py` | Prize image: user upload, AI full-body generation, or local `compose` layouts (card / circle / badge) |
| C–D | `scripts/build_game.py` | Validates the gate, then injects `__MOLE_CONFIG__` into the template and emits both build flavours |
| E | `scripts/verify_game.py` | Headless regression over both builds via Playwright + Chrome DevTools Protocol against local Edge |

`assets/game_template.html` holds every variable as a `__MOLE_CONFIG__` placeholder — **you change the config, never the template**.

### The game itself

- 4 difficulty tiers out of the box (轻松 / 普通 / 困难 / 地狱) with configurable level counts and lives — the reference build runs 9 / 9 / 12 / 15 levels and 15 / 10 / 8 / 6 lives
- 11-expression avatar: different faces for popping up (mockery), being hit (pain), and escaping
- Gold / colour eggs grant extra lives; when lives are capped the reward converts into bonus score
- Obstacles: black bird, bomb, nuke (harder tiers only)
- Clearing a tier opens an easter-egg page with confetti and a "claim your prize" image
- Procedural WebAudio SFX, no external assets, fully responsive

### Four hard red lines (enforced by scripts, not by good intentions)

`build_game.py` refuses to build unless `gate.json` says the gate was passed:

1. **The photo source must be chosen by the user** — upload / local path / "pick a few from my library". The skill must stop and wait; it may never go hunting through the photo library on its own.
2. **The expression contact sheet must be shown and confirmed, on a pure flat background** — only `magenta / green / blue / white` chroma backgrounds are allowed. A sheet flagged `FAIL` by the background check may not be presented as "approvable".
3. **Prize image: source and coverage must be asked first** — upload / auto-generate / local compose, plus "one shared image" vs "one per difficulty".
4. **Every difficulty except 轻松 (easy) must ship its own prize image** — `easy` has none by design; `normal / hard / hell` each need a finalised one or the build fails.

---

## Install

### Option A — One-click installer (GUI, recommended)

Download `photo-mole-game-installer.exe` from [Releases](https://github.com/jaja1620/photo-mole-game/releases/latest) (10.0 MB, single file, no Python required on the target machine).

| Step | What happens |
| --- | --- |
| 1 | Double-click the exe — a GUI opens (Tkinter, Chinese UI) |
| 2 | **Auto-detect**: the installer scans 28 agent config directories and pre-ticks every agent it finds on your machine; the rest show as "not detected" |
| 3 | Every row shows its target directory; click **浏览…** on a row to override that path |
| 4 | **一键安装到勾选项** installs the bundled skill (v1.2.0, 18 files) into `<agent-skills-dir>/photo-mole-game` |
| 5 | No agent detected, or you want a private location? Use **选择自定义目录安装…** and pick any directory |

Behaviour details that matter:

- **Idempotent** — if the target already matches the payload byte-for-byte, it reports `[UNCHANGED]` and writes nothing
- **Backup before overwrite** (on by default) — the previous install is renamed to `photo-mole-game.bak-YYYYMMDD-HHMMSS` before the new one lands
- **Result log** — each line is `[OK]` / `[UPDATE]` / `[UNCHANGED]` / `[SKIP]` / `[ERR]` plus the path, with a success/skipped/failed summary
- **System directories are refused** — installing into `C:\Windows`, `C:\Program Files`, etc. fails with an explicit error

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

Or unzip `photo-mole-game_v1.2.0.zip` (from Releases) straight into the skills directory — the archive root is already `photo-mole-game/`.

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
| Any agent (portable) | `~/.agents/skills` |

The one-click installer ships exactly this table (28 entries) and detects an agent by the presence of its config directory.

### Verify the install

```bash
pip install pillow numpy opencv-python
python ~/.workbuddy/skills/photo-mole-game/scripts/gate.py --file /tmp/g.json --show
python ~/.workbuddy/skills/photo-mole-game/scripts/build_game.py --help
```

If both commands run, the package is complete. `SKILL.md` frontmatter `version` and `manifest.json` `version` should both read `1.2.0`.

---

## Using it

Just ask your agent, in plain language:

> "用我这张照片做个打地鼠小游戏" / "Make a whack-a-mole game out of this photo"

The agent then:

1. asks **where the photo comes from** (upload / path / pick from library) and waits;
2. generates 11 expressions on a flat chroma background, assembles a contact sheet and asks **all pass / redo all / redo these**;
3. asks **where the prize image comes from** and whether all difficulties share one;
4. writes `config.json` (title, tiers, levels, lives, rewards, easter-egg copy);
5. builds the folder version and the single-file HTML, then runs the headless regression;
6. hands you a double-clickable `.html`.

Typical timings on a local GPU (flux.2 klein 4B / z-image-turbo via `sd-server` on `127.0.0.1:8790`): 11 expressions ≈ 2–4 min, cutout ≈ 20 s, build + verify ≈ 30 s.

Anything goes wrong, real-world traps are catalogued in `skill/references/pitfalls.md`.

---

## Repository layout

```
skill/                 the skill package itself (v1.2.0, 18 files)
  SKILL.md             pipeline spec + the four red lines
  scripts/             gate / expressions / sheet / cutout / prize / build / verify
  assets/              game_template.html (all variables are __MOLE_CONFIG__)
  references/          config schema, expression list, pitfalls
  examples/            config.qiaotan.json, config.minimal.json
  install.ps1          PowerShell installer (backup + verify)
  manifest.json        per-file sha256
installer/             source of the GUI one-click installer
  photo_mole_installer.py    Tkinter GUI + CLI, single file
  build.ps1 / build.bat      reproducible PyInstaller build (payload = ../skill)
  photo-mole-game-installer.spec   portable spec, same payload resolution
CHECKSUMS.txt          sha256 of the release assets
```

## Release assets

| Asset | Size | SHA256 |
| --- | --- | --- |
| `photo-mole-game-installer.exe` | 10,464,319 B | `69E704925D51751801CB2831468022B48EC69DDDAEE0D0C736717A5E06D474ED` |
| `photo-mole-game_v1.2.0.zip` | 193,733 B | `D2B8DDF4A6165D90E95C644B327CB8B121C99A2A784285FB6D1C101AFE380D4E` |

## Changelog

| Version | Highlights |
| --- | --- |
| 1.2.0 | Pure-colour background rule + background check before showing the sheet; prize coverage per difficulty (`easy` has none, the other three must); `gen_prize.py --mode compose` local layout synthesis; `--chroma auto` cutout reading `manifest.json` |
| 1.1.0 | Gate hard-fail: `build_game.py` refuses to build without `gate.json`; contact-sheet confirmation loop; prize image source question |
| 1.0.0 | First pipeline: expressions → cutout → config → build → headless verify |

## License

MIT. Author: **JaJa**.

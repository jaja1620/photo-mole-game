# -*- coding: utf-8 -*-
"""
photo-mole-game 技能 · 主流 Agent 一键安装器 v1.2.0

功能：
  1) GUI（Tkinter）：自动检测本机主流 Agent 软件的技能目录，一键安装到已勾选项；
     也支持手动勾选 Agent、逐行修改目标目录，或直接指定任意目录安装。
  2) CLI（--cli）：供自测与静默部署，支持 --list / --install --all / --install --agents / --dest。

技能载荷（payload）在打包时通过 PyInstaller --add-data 内嵌为 skill_payload/photo-mole-game，
运行时从 sys._MEIPASS 读取；开发态则回退到本目录下的 skill_payload 或备份目录。

作者：Marvis file-agent
"""

import argparse
import hashlib
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback

APP_TITLE = "photo-mole-game 技能一键安装器 v1.2.0"
SKILL_NAME = "photo-mole-game"
SKILL_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Agent 路径表（用户级 / 全局 skills 目录）
# detect: 任一目录存在 -> 视为已安装
# skills: 安装目录（skills 根），实际目标为 <skills>/photo-mole-game
# ---------------------------------------------------------------------------
AGENTS = [
    {"name": "Amp",            "key": "amp",            "detect": ["~/.config/agents"],               "skills": "~/.config/agents/skills"},
    {"name": "Antigravity",    "key": "antigravity",    "detect": ["~/.gemini/antigravity", "~/.gemini"], "skills": "~/.gemini/antigravity/skills"},
    {"name": "Claude Code",    "key": "claude-code",    "detect": ["~/.claude"],                      "skills": "~/.claude/skills"},
    {"name": "Clawdbot",       "key": "clawdbot",       "detect": ["~/.clawdbot"],                    "skills": "~/.clawdbot/skills"},
    {"name": "Cline",          "key": "cline",          "detect": ["~/.cline"],                       "skills": "~/.cline/skills"},
    {"name": "CodeBuddy",      "key": "codebuddy",      "detect": ["~/.codebuddy"],                   "skills": "~/.codebuddy/skills"},
    {"name": "Codex",          "key": "codex",          "detect": ["~/.codex"],                       "skills": "~/.codex/skills"},
    {"name": "Command Code",   "key": "command-code",   "detect": ["~/.commandcode"],                 "skills": "~/.commandcode/skills"},
    {"name": "Cursor",         "key": "cursor",         "detect": ["~/.cursor"],                      "skills": "~/.cursor/skills"},
    {"name": "Droid",          "key": "droid",          "detect": ["~/.factory"],                     "skills": "~/.factory/skills"},
    {"name": "Gemini CLI",     "key": "gemini-cli",     "detect": ["~/.gemini"],                      "skills": "~/.gemini/skills"},
    {"name": "GitHub Copilot", "key": "github-copilot", "detect": ["~/.copilot"],                     "skills": "~/.copilot/skills"},
    {"name": "Goose",          "key": "goose",          "detect": ["~/.config/goose"],                "skills": "~/.config/goose/skills"},
    {"name": "Kilo Code",      "key": "kilo",           "detect": ["~/.kilocode"],                    "skills": "~/.kilocode/skills"},
    {"name": "Kiro CLI",       "key": "kiro-cli",       "detect": ["~/.kiro"],                        "skills": "~/.kiro/skills"},
    {"name": "MCPJam",         "key": "mcpjam",         "detect": ["~/.mcpjam"],                      "skills": "~/.mcpjam/skills"},
    {"name": "Neovate",        "key": "neovate",        "detect": ["~/.neovate"],                     "skills": "~/.neovate/skills"},
    {"name": "OpenCode",       "key": "opencode",       "detect": ["~/.config/opencode"],             "skills": "~/.config/opencode/skills"},
    {"name": "OpenHands",      "key": "openhands",      "detect": ["~/.openhands"],                   "skills": "~/.openhands/skills"},
    {"name": "Pi",             "key": "pi",             "detect": ["~/.pi"],                          "skills": "~/.pi/agent/skills"},
    {"name": "Qoder",          "key": "qoder",          "detect": ["~/.qoder"],                       "skills": "~/.qoder/skills"},
    {"name": "Qwen Code",      "key": "qwen-code",      "detect": ["~/.qwen"],                        "skills": "~/.qwen/skills"},
    {"name": "Roo Code",       "key": "roo",            "detect": ["~/.roo"],                          "skills": "~/.roo/skills"},
    {"name": "Trae",           "key": "trae",           "detect": ["~/.trae"],                        "skills": "~/.trae/skills"},
    {"name": "Windsurf",       "key": "windsurf",       "detect": ["~/.codeium/windsurf", "~/.codeium"], "skills": "~/.codeium/windsurf/skills"},
    {"name": "Zencoder",       "key": "zencoder",       "detect": ["~/.zencoder"],                    "skills": "~/.zencoder/skills"},
    {"name": "WorkBuddy",      "key": "workbuddy",      "detect": ["~/.workbuddy"],                   "skills": "~/.workbuddy/skills"},
    {"name": "通用互操作目录", "key": "agents",         "detect": ["~/.agents"],                      "skills": "~/.agents/skills"},
]

# 禁止写入的系统目录（前缀匹配）
FORBIDDEN_DIRS = [
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
    r"C:\Users\Default",
]

COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
LOG_PATH = os.path.join(tempfile.gettempdir(), "photo-mole-installer.log")


# ---------------------------------------------------------------------------
# 日志（--windowed 无控制台时用于排查）
# ---------------------------------------------------------------------------
def log_line(text):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as f:
            f.write("[%s] %s\n" % (stamp, text))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 载荷相关
# ---------------------------------------------------------------------------
def payload_root():
    """定位内嵌 / 本地载荷目录。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "skill_payload", SKILL_NAME))
    candidates += [
        os.path.join(here, "skill_payload", SKILL_NAME),
        os.path.join(here, "..", "backup", "photo-mole-game_v1.2.0"),
        os.path.join(here, "..", "photo-mole-game"),
    ]
    for c in candidates:
        c = os.path.abspath(c)
        if os.path.isfile(os.path.join(c, "SKILL.md")):
            return c
    raise RuntimeError("未找到技能载荷目录（skill_payload/photo-mole-game）")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _skip_name(name):
    return name == "__pycache__" or name.endswith(".pyc") or name == ".DS_Store"


def build_manifest(root):
    """返回 [(相对路径 posix, 绝对路径, 大小, sha256)]，排除 __pycache__ / *.pyc / .DS_Store。"""
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _skip_name(d)]
        for fn in filenames:
            if _skip_name(fn):
                continue
            ap = os.path.join(dirpath, fn)
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            items.append((rel, ap, os.path.getsize(ap), sha256_file(ap)))
    items.sort(key=lambda x: x[0])
    return items


VER_RE = re.compile(r"^version:\s*([^\s#]+)", re.M)


def parse_skill_version(skill_md):
    """解析 SKILL.md frontmatter 中的 version: 字段，失败返回 None。"""
    try:
        text = open(skill_md, "r", encoding="utf-8", errors="replace").read()
    except Exception:
        return None
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    block = m.group(1) if m else text
    mm = VER_RE.search(block)
    return mm.group(1).strip() if mm else None


# ---------------------------------------------------------------------------
# 安装核心
# ---------------------------------------------------------------------------
def is_forbidden_dir(path):
    """命中系统目录 / 磁盘根目录时返回原因字符串，否则 None。"""
    p = os.path.normcase(os.path.abspath(path))
    for f in FORBIDDEN_DIRS:
        fn = os.path.normcase(f)
        if p == fn or p.startswith(fn + os.sep):
            return f
    drive, tail = os.path.splitdrive(p)
    if tail.strip("\\") == "":
        return "磁盘根目录（%s）" % drive
    return None


def diff_against_payload(target, manifest):
    """返回与载荷不一致（缺失或 sha256 不同）的相对路径列表。"""
    bad = []
    for rel, _ap, _size, digest in manifest:
        tp = os.path.join(target, rel.replace("/", os.sep))
        if not os.path.isfile(tp) or sha256_file(tp) != digest:
            bad.append(rel)
    return bad


def install_to(target, manifest, overwrite=True):
    """
    执行一次安装。返回 (tag, message)，tag ∈ OK / UPDATE / UNCHANGED / SKIP / ERR。
    message 为对应规格的输出行（不含 tag）。
    """
    reason = is_forbidden_dir(os.path.dirname(target))
    if reason:
        return "ERR", "目标目录位于系统受保护位置，已拒绝：%s（%s）" % (target, reason)

    payload_dir = payload_root()
    parent = os.path.dirname(target)
    try:
        os.makedirs(parent, exist_ok=True)
    except Exception as e:
        return "ERR", "无法创建父目录 %s：%s" % (parent, e)

    if os.path.exists(target):
        if not os.path.isdir(target):
            return "ERR", "目标已存在且不是目录：%s" % target
        bad = diff_against_payload(target, manifest)
        if not bad:
            ver = parse_skill_version(os.path.join(target, "SKILL.md")) or "?"
            return "UNCHANGED", "已是最新 %s（v%s）" % (target, ver)
        if not overwrite:
            return "SKIP", "已存在且未勾选覆盖 %s" % target
        # 覆盖：先整体改名备份
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bak = "%s.bak-%s" % (target, stamp)
        n = 1
        while os.path.exists(bak):
            bak = "%s.bak-%s-%d" % (target, stamp, n)
            n += 1
        try:
            os.rename(target, bak)
        except Exception as e:
            return "ERR", "备份失败，已保留原目录 %s：%s" % (target, e)
        try:
            shutil.copytree(payload_dir, target, ignore=COPY_IGNORE)
        except Exception as e:
            # 复制失败：尽量回滚到备份，避免用户目录处于半成品状态
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
                os.rename(bak, target)
                return "ERR", "复制失败已回滚 %s：%s" % (target, e)
            except Exception:
                return "ERR", "复制失败且回滚失败 %s：%s（备份：%s）" % (target, e, bak)
        ver = parse_skill_version(os.path.join(target, "SKILL.md"))
        if not ver:
            return "ERR", "已覆盖但校验失败：SKILL.md 缺失或版本号无法解析 %s" % target
        return "UPDATE", "覆盖 %s（备份：%s）v%s" % (target, bak, ver)

    # 全新安装
    try:
        shutil.copytree(payload_dir, target, ignore=COPY_IGNORE)
    except Exception as e:
        return "ERR", "复制失败 %s：%s" % (target, e)
    ver = parse_skill_version(os.path.join(target, "SKILL.md"))
    if not ver:
        return "ERR", "校验失败：SKILL.md 缺失或版本号无法解析 %s" % target
    return "OK", "新增 %s（v%s）" % (target, ver)


def format_line(tag, message):
    return "[%s] %s" % (tag, message)


# ---------------------------------------------------------------------------
# Agent 检测
# ---------------------------------------------------------------------------
def expand(p):
    return os.path.abspath(os.path.expanduser(p))


def agent_target(agent):
    return os.path.join(expand(agent["skills"]), SKILL_NAME)


def agent_detected(agent):
    return any(os.path.exists(expand(d)) for d in agent["detect"])


def detect_hint(agent):
    for d in agent["detect"]:
        if os.path.exists(expand(d)):
            return expand(d)
    return ""


def installed_version(target):
    skill_md = os.path.join(target, "SKILL.md")
    if not os.path.isfile(skill_md):
        return None
    return parse_skill_version(skill_md)


def detect_all():
    rows = []
    for a in AGENTS:
        tgt = agent_target(a)
        rows.append({
            "agent": a,
            "detected": agent_detected(a),
            "hint": detect_hint(a),
            "target": tgt,
            "version": installed_version(tgt),
        })
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _console_encoding():
    """控制台/管道输出编码：跟随控制台代码页（中文系统通常 936），避免乱码。"""
    forced = os.environ.get("PHOTO_MOLE_OUT_ENCODING", "").strip()
    if forced:
        return forced
    try:
        import ctypes
        cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        if cp:
            return "cp%d" % cp
    except Exception:
        pass
    try:
        import locale
        return locale.getpreferredencoding(False)
    except Exception:
        return "utf-8"


def _ensure_std_streams():
    """--windowed 构建下恢复 stdout/stderr（控制台或管道）。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    enc = _console_encoding()
    try:
        import ctypes
        import msvcrt
        k = ctypes.windll.kernel32
        k.AttachConsole(-1)  # ATTACH_PARENT_PROCESS
        for std_id, name in ((-11, "stdout"), (-12, "stderr")):
            if getattr(sys, name) is not None:
                continue
            try:
                h = k.GetStdHandle(std_id)
                if h and h not in (0, -1):
                    fd = msvcrt.open_osfhandle(h, os.O_WRONLY)
                    setattr(sys, name, os.fdopen(fd, "w", encoding=enc, errors="replace", buffering=1))
                else:
                    raise OSError("no handle")
            except Exception:
                try:
                    setattr(sys, name, open("CONOUT$", "w", encoding=enc, errors="replace", buffering=1))
                except Exception:
                    setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    except Exception:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")


def out(text=""):
    try:
        print(text, flush=True)
    except Exception:
        pass
    log_line(text)


def cli_list():
    rows = detect_all()
    out("photo-mole-game 技能一键安装器 v1.2.0 · Agent 检测结果")
    out("载荷版本：v%s  载荷目录：%s" % (SKILL_VERSION, payload_root()))
    out("-" * 132)
    out("%-16s %-16s %-8s %-14s %s" % ("显示名", "agent key", "检测", "已装版本", "目标目录"))
    out("-" * 132)
    hit = 0
    for r in rows:
        a = r["agent"]
        detected = "已检测" if r["detected"] else "未检测"
        if r["detected"]:
            hit += 1
        ver = ("v" + r["version"]) if r["version"] else "-"
        name = a["name"]
        # 中文列宽对齐（全角字符按 2 计）
        pad = 16 - (len(name) + sum(1 for ch in name if ord(ch) > 127))
        out("%s%s %-16s %-8s %-14s %s" % (name, " " * max(pad, 1), a["key"], detected, ver, r["target"]))
    out("-" * 132)
    out("汇总：共 %d 个 Agent，已检测 %d 个，未检测 %d 个" % (len(rows), hit, len(rows) - hit))
    return 0


def run_install(targets, overwrite=True):
    """targets: [(label, target_path)]；返回 (ok, skip, fail)，逐条输出。"""
    manifest = build_manifest(payload_root())
    ok = skip = fail = 0
    for label, target in targets:
        try:
            tag, msg = install_to(target, manifest, overwrite)
        except Exception as e:
            tag, msg = "ERR", "%s：%s" % (label, e)
            log_line(traceback.format_exc())
        if tag in ("OK", "UPDATE"):
            ok += 1
        elif tag in ("UNCHANGED", "SKIP"):
            skip += 1
        else:
            fail += 1
            msg = "%s %s" % (label, msg) if not msg.startswith(label) else msg
        out(format_line(tag, msg))
    out("汇总：成功 %d / 跳过 %d / 失败 %d" % (ok, skip, fail))
    return ok, skip, fail


def cli_install(args):
    if args.dest:
        dest = expand(args.dest)
        reason = is_forbidden_dir(dest)
        if reason:
            out(format_line("ERR", "目标目录位于系统受保护位置，已拒绝：%s（%s）" % (dest, reason)))
            out("汇总：成功 0 / 跳过 0 / 失败 1")
            return 1
        targets = [("自定义目录", os.path.join(dest, SKILL_NAME))]
    elif args.all:
        rows = [r for r in detect_all() if r["detected"]]
        if not rows:
            out(format_line("ERR", "未检测到任何已安装的 Agent，请使用 --agents 或 --dest 指定目标"))
            out("汇总：成功 0 / 跳过 0 / 失败 1")
            return 1
        targets = [(r["agent"]["name"], r["target"]) for r in rows]
    elif args.agents:
        keys = [k.strip() for k in args.agents.split(",") if k.strip()]
        by_key = {a["key"]: a for a in AGENTS}
        targets = []
        bad = False
        for k in keys:
            a = by_key.get(k)
            if not a:
                out(format_line("ERR", "未知的 agent key：%s" % k))
                bad = True
                continue
            targets.append((a["name"], agent_target(a)))
        if bad and not targets:
            out("汇总：成功 0 / 跳过 0 / 失败 1")
            return 1
    else:
        out(format_line("ERR", "缺少安装目标：请使用 --all、--agents 或 --dest 之一"))
        out("汇总：成功 0 / 跳过 0 / 失败 1")
        return 1

    if not args.yes:
        out("即将安装到以下 %d 个目标（加 --yes 可跳过此提示）：" % len(targets))
        for label, t in targets:
            out("  - %s -> %s" % (label, t))

    _ok, _skip, fail = run_install(targets, overwrite=not args.no_overwrite)
    return 1 if fail else 0


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
def build_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    manifest = build_manifest(payload_root())
    total_bytes = sum(i[2] for i in manifest)

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("1000x700")
    root.minsize(900, 580)
    try:
        root.iconify()
        root.deiconify()
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except Exception:
        pass

    # ----- 顶部信息条 -----
    head = tk.Frame(root, bg="#0f172a")
    head.pack(fill="x")
    tk.Label(head, text="photo-mole-game 技能一键安装器", bg="#0f172a", fg="#ffffff",
             font=("Microsoft YaHei UI", 14, "bold")).pack(side="left", padx=14, pady=10)
    info = "版本 v%s   ·   载荷 %d 个文件   ·   %s 字节（%.1f KB）" % (
        SKILL_VERSION, len(manifest), format(total_bytes, ","), total_bytes / 1024.0)
    tk.Label(head, text=info, bg="#0f172a", fg="#9fb3c8",
             font=("Microsoft YaHei UI", 9)).pack(side="left", padx=6, pady=12)

    # ----- 工具栏 -----
    bar = tk.Frame(root)
    bar.pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(bar, text="检测到的 Agent 默认勾选，可手动调整；目标目录可逐行「浏览…」修改。",
             fg="#555").pack(side="left")
    btn_redetect = ttk.Button(bar, text="重新检测")
    btn_sel_detected = ttk.Button(bar, text="全选已检测")
    btn_clear = ttk.Button(bar, text="全不选")
    btn_clear.pack(side="right", padx=4)
    btn_sel_detected.pack(side="right", padx=4)
    btn_redetect.pack(side="right", padx=4)

    # ----- 列表（Canvas + Frame） -----
    wrap = tk.Frame(root, bd=1, relief="solid")
    wrap.pack(fill="both", expand=True, padx=12, pady=4)

    header = tk.Frame(wrap, bg="#eef2f7")
    header.pack(fill="x")
    tk.Label(header, text="选择", width=6, bg="#eef2f7", anchor="w").pack(side="left", padx=(8, 0), pady=4)
    tk.Label(header, text="Agent", width=26, bg="#eef2f7", anchor="w").pack(side="left")
    tk.Label(header, text="目标安装目录", bg="#eef2f7", anchor="w").pack(side="left", fill="x", expand=True)
    tk.Label(header, text="状态", width=14, bg="#eef2f7", anchor="w").pack(side="left")

    canvas = tk.Canvas(wrap, highlightthickness=0)
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas)
    canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
        canvas.find_all()[0], width=e.width))

    def _wheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _wheel)

    rows = []
    state = {"busy": False}

    # ----- 选项 -----
    opt = tk.Frame(root)
    opt.pack(fill="x", padx=12, pady=(2, 0))
    overwrite_var = tk.BooleanVar(value=True)
    tk.Checkbutton(opt, text="覆盖已存在的安装（覆盖前自动备份为 photo-mole-game.bak-时间戳）",
                   variable=overwrite_var).pack(side="left")

    # ----- 主操作 -----
    actions = tk.Frame(root)
    actions.pack(fill="x", padx=12, pady=(6, 2))
    btn_install = ttk.Button(actions, text="一键安装到已勾选项")
    btn_custom = ttk.Button(actions, text="选择自定义目录安装…")
    btn_install.pack(side="left")
    btn_custom.pack(side="left", padx=8)

    # ----- 状态条（独立一行，避免与按钮/进度条重叠） -----
    status_row = tk.Frame(root)
    status_row.pack(fill="x", padx=12, pady=(0, 4))
    status_lbl = tk.Label(status_row, text="就绪", fg="#666", anchor="w")
    status_lbl.pack(side="left")
    prog = ttk.Progressbar(status_row, mode="determinate", length=240)
    prog.pack(side="right")

    # ----- 结果区 -----
    res_frame = tk.Frame(root)
    res_frame.pack(fill="both", padx=12, pady=(0, 10))
    tk.Label(res_frame, text="执行结果", anchor="w").pack(fill="x")
    text = tk.Text(res_frame, height=9, wrap="none", state="disabled",
                   font=("Consolas", 9), bg="#0b0b0c", fg="#d6d6d6")
    tb = ttk.Scrollbar(res_frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=tb.set)
    tb.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    text.tag_configure("OK", foreground="#22c55e")
    text.tag_configure("UPDATE", foreground="#3b82f6")
    text.tag_configure("UNCHANGED", foreground="#9ca3af")
    text.tag_configure("SKIP", foreground="#f59e0b")
    text.tag_configure("ERR", foreground="#ef4444")
    text.tag_configure("SUM", foreground="#ffffff")

    msg_q = queue.Queue()

    def push(kind, line):
        msg_q.put((kind, line))

    def drain():
        try:
            while True:
                kind, line = msg_q.get_nowait()
                text.configure(state="normal")
                text.insert("end", line + "\n", (kind,))
                text.see("end")
                text.configure(state="disabled")
                log_line(line)
        except queue.Empty:
            pass
        if state["busy"]:
            root.after(120, drain)

    def set_busy(busy, label="就绪"):
        state["busy"] = busy
        st = "disabled" if busy else "normal"
        for b in (btn_install, btn_custom, btn_redetect, btn_sel_detected, btn_clear):
            b.configure(state=st)
        for r in rows:
            r["chk"].configure(state=st)
            r["btn"].configure(state=st)
        status_lbl.configure(text=label)

    # ----- 行构建 -----
    def make_row(parent, idx):
        r = {}
        fr = tk.Frame(parent, bg="#ffffff" if idx % 2 == 0 else "#fafbfc")
        fr.pack(fill="x")
        var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(fr, variable=var, bg=fr["bg"], activebackground=fr["bg"])
        chk.pack(side="left", padx=(8, 0))
        name_lbl = tk.Label(fr, text="", width=26, anchor="w", bg=fr["bg"])
        name_lbl.pack(side="left")
        path_var = tk.StringVar()
        ent = tk.Entry(fr, textvariable=path_var, state="readonly", relief="flat",
                       readonlybackground=fr["bg"], fg="#333")
        ent.pack(side="left", fill="x", expand=True, padx=(0, 4))
        btn = ttk.Button(fr, text="浏览…", width=7)
        btn.pack(side="left", padx=(0, 4))
        st_lbl = tk.Label(fr, text="", width=14, anchor="w", bg=fr["bg"])
        st_lbl.pack(side="left")
        r.update({"frame": fr, "var": var, "chk": chk, "name": name_lbl,
                  "path_var": path_var, "btn": btn, "status": st_lbl,
                  "custom": False})
        return r

    def refresh_status(r):
        a = r["agent"]
        if r["custom"]:
            r["status"].configure(text="自定义", fg="#b45309")
            return
        ver = installed_version(r["path_var"].get())
        if ver:
            txt = "已装 v%s" % ver
            if ver == SKILL_VERSION:
                r["status"].configure(text=txt, fg="#15803d")
            else:
                r["status"].configure(text=txt + "（旧）", fg="#b91c1c")
        elif r["detected"]:
            r["status"].configure(text="已检测", fg="#0f766e")
        else:
            r["status"].configure(text="未检测", fg="#6b7280")

    def browse(r):
        d = filedialog.askdirectory(title="选择该 Agent 的技能安装目录")
        if not d:
            return
        tgt = os.path.join(os.path.normpath(d), SKILL_NAME)
        r["path_var"].set(tgt)
        r["custom"] = True
        refresh_status(r)

    def rebuild():
        for w in inner.winfo_children():
            w.destroy()
        rows.clear()
        detected_rows = detect_all()
        for i, d in enumerate(detected_rows):
            r = make_row(inner, i)
            r["agent"] = d["agent"]
            r["detected"] = d["detected"]
            r["default_target"] = d["target"]
            a = d["agent"]
            r["name"].configure(text="%s  (%s)" % (a["name"], a["key"]))
            r["path_var"].set(d["target"])
            r["var"].set(d["detected"])
            r["btn"].configure(command=lambda rr=r: browse(rr))
            refresh_status(r)
            rows.append(r)
        set_busy(False, "共 %d 个 Agent，已检测 %d 个" % (
            len(detected_rows), sum(1 for x in detected_rows if x["detected"])))

    # ----- 安装执行 -----
    def start_install(targets):
        if not targets:
            messagebox.showinfo("提示", "请先勾选至少一个 Agent，或使用「选择自定义目录安装…」。")
            return
        set_busy(True, "正在安装 0/%d …" % len(targets))
        prog.configure(maximum=len(targets), value=0)
        push("SUM", "-" * 96)
        push("SUM", "开始安装，共 %d 个目标（覆盖=%s）" % (
            len(targets), "是" if overwrite_var.get() else "否"))

        def worker():
            man = manifest
            ok = skip = fail = 0
            for i, (label, tgt) in enumerate(targets, 1):
                push("SUM", "")  # 占位保持顺序
                try:
                    tag, msg = install_to(tgt, man, overwrite_var.get())
                except Exception as e:
                    tag, msg = "ERR", "%s：%s" % (label, e)
                if tag in ("OK", "UPDATE"):
                    ok += 1
                elif tag in ("UNCHANGED", "SKIP"):
                    skip += 1
                else:
                    fail += 1
                    if not msg.startswith(label):
                        msg = "%s %s" % (label, msg)
                push(tag, format_line(tag, msg))
                root.after(0, lambda v=i: prog.configure(value=v))
                root.after(0, lambda v=i, n=len(targets): status_lbl.configure(
                    text="正在安装 %d/%d …" % (v, n)))
            push("SUM", "汇总：成功 %d / 跳过 %d / 失败 %d" % (ok, skip, fail))
            root.after(0, lambda: finish(ok, skip, fail))

        threading.Thread(target=worker, daemon=True).start()
        drain()

    def finish(ok, skip, fail):
        set_busy(False, "完成：成功 %d / 跳过 %d / 失败 %d" % (ok, skip, fail))
        for r in rows:
            refresh_status(r)
        if fail:
            messagebox.showwarning("安装完成（有失败）",
                                   "成功 %d 个，跳过 %d 个，失败 %d 个。\n详见结果区。" % (ok, skip, fail))
        else:
            messagebox.showinfo("安装完成",
                                "成功 %d 个，跳过 %d 个。\n技能目录已就绪，重启对应 Agent 即可使用。" % (ok, skip))

    def do_install_selected():
        targets = []
        for r in rows:
            if r["var"].get():
                targets.append((r["agent"]["name"], r["path_var"].get()))
        start_install(targets)

    def do_install_custom():
        d = filedialog.askdirectory(title="选择安装目录（将在其中创建 photo-mole-game）")
        if not d:
            return
        tgt = os.path.join(os.path.normpath(d), SKILL_NAME)
        reason = is_forbidden_dir(os.path.dirname(tgt))
        if reason:
            messagebox.showerror("位置不允许", "所选目录位于系统受保护位置：%s\n请换一个目录。" % reason)
            return
        if not messagebox.askyesno(
                "确认安装位置",
                "将安装到：\n\n%s\n\n确认继续？" % tgt):
            return
        start_install([("自定义目录", tgt)])

    btn_redetect.configure(command=rebuild)
    btn_sel_detected.configure(command=lambda: [r["var"].set(True) for r in rows if r["detected"]])
    btn_clear.configure(command=lambda: [r["var"].set(False) for r in rows])
    btn_install.configure(command=do_install_selected)
    btn_custom.configure(command=do_install_custom)

    rebuild()
    log_line("GUI 启动，载荷 %d 个文件 / %d 字节，载荷目录 %s" % (
        len(manifest), total_bytes, payload_root()))
    root.mainloop()
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--cli" not in argv:
        # 无参数（或非 CLI）→ GUI
        try:
            return build_gui()
        except Exception:
            log_line("GUI 启动失败：\n" + traceback.format_exc())
            raise

    _ensure_std_streams()
    log_line("=" * 60 + " CLI " + " ".join(argv))

    p = argparse.ArgumentParser(prog="photo-mole-game-installer",
                                description="photo-mole-game 技能一键安装器 v1.2.0（CLI 模式）")
    p.add_argument("--cli", action="store_true", help="CLI 模式")
    p.add_argument("--list", action="store_true", help="列出所有 Agent 的检测结果与目标路径")
    p.add_argument("--install", action="store_true", help="执行安装")
    p.add_argument("--all", action="store_true", help="安装到所有已检测到的 Agent")
    p.add_argument("--yes", action="store_true", help="跳过确认提示")
    p.add_argument("--agents", default="", help="逗号分隔的 agent key 列表")
    p.add_argument("--dest", default="", help="自定义安装根目录（目标为其下 photo-mole-game）")
    p.add_argument("--no-overwrite", action="store_true", help="不覆盖已存在的旧版本（输出 SKIP）")
    args = p.parse_args(argv)

    if args.list:
        return cli_list()
    if args.install:
        return cli_install(args)
    out("用法：photo-mole-game-installer.exe --cli [--list | --install --all --yes | --install --agents a,b | --install --dest DIR]")
    out("      不带 --cli 启动则打开图形界面。")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
    sys.exit(code)

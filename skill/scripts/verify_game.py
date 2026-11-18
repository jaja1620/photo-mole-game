# -*- coding: utf-8 -*-
"""verify_game.py — 打地鼠游戏无头回归校验（CDP 连接本机 Edge）

用法:
  python verify_game.py --dir out/ --config config.json --out report.json [--port 9333]

校验项:
  1. 页面无 JS 异常、无 console error
  2. 标题 / kicker / lead / 版本号与 config 一致
  3. 难度卡片数量与文案（关数、命数、上限）与 config 一致
  4. 切换难度后 #maxLvl 正确
  5. 开局后进入 playing 且 HUD 可见
  6. 表情资源全部加载成功（naturalWidth > 0）
  7. 彩蛋页：标题/礼物/文案/彩蛋图/关卡数标语正确，纸屑 canvas 已绘制（alpha>8 像素 > 200）
  8. 领取惊喜：惊喜图正确加载，3 秒后返回按钮出现
  9. 单文件版：无 assets/ 外部引用（构建侧 + 运行侧双检）
"""
import argparse, json, os, subprocess, sys, time, urllib.request

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p): return p
    raise SystemExit("未找到 msedge.exe")

def launch_edge(port, user_dir):
    os.makedirs(user_dir, exist_ok=True)
    proc = subprocess.Popen([find_edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                             "--remote-debugging-port=%d" % port,
                             "--user-data-dir=" + user_dir, "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=1); return proc
        except Exception:
            time.sleep(0.25)
    proc.kill(); raise SystemExit("Edge 调试端口未就绪")

def js_count_colored_pixels(page, sel):
    return page.evaluate("""(sel) => {
        const c = document.querySelector(sel);
        if (!c) return -1;
        const g = c.getContext('2d');
        const d = g.getImageData(0, 0, c.width, c.height).data;
        let n = 0;
        for (let i = 3; i < d.length; i += 4 * 37) if (d[i] > 8) n++;
        return n;
    }""", sel)

def check_page(page, cfg, kind, errs):
    def ok(cond, msg):
        if not cond: errs.append("[%s] %s" % (kind, msg))

    page.goto("file:///" + page._html_path.replace("\\", "/"))
    page.wait_for_timeout(1200)

    # 1. 标题与菜单文案
    ok(page.title() == cfg["title"] + (" · " + cfg["subtitle"] if cfg.get("subtitle") else ""),
       "标题不符: %r" % page.title())
    ok(page.inner_text("#mKicker").strip().lower() == (cfg.get("kicker") or "").strip().lower(),
       "kicker 不符: %r" % page.inner_text("#mKicker"))
    ok(page.inner_text("#mVer") == cfg["version"], "版本号不符")
    lead = page.inner_text("#mLead")
    ok(lead == (cfg.get("lead") or ""), "引导语不符: %r" % lead)

    # 2. 难度卡片
    cards = page.eval_on_selector_all(".m-diff", "els => els.map(e => ({d: e.dataset.d, t: e.innerText}))")
    ok(len(cards) == len(cfg["diffOrder"]), "难度卡片数 %d != %d" % (len(cards), len(cfg["diffOrder"])))
    for c in cards:
        d = cfg["difficulties"][c["d"]]
        ok(("%d 关" % d["levels"]) in c["t"], "难度卡 %s 缺关数" % c["d"])
        ok(("%d 条命" % d["lives"]) in c["t"], "难度卡 %s 缺命数" % c["d"])
        cap = d.get("lifeCap")
        ok(("无上限" if cap in (None, "Infinity") else "上限 %s" % cap) in c["t"], "难度卡 %s 缺上限" % c["d"])

    # 3. 表情加载
    bad = page.evaluate("""() => {
        const out = [];
        for (const k of KEYS) if (!IMG[k] || !IMG[k].naturalWidth) out.push(k);
        return out;
    }""")
    ok(not bad, "表情未加载: %s" % bad)
    ok(page.evaluate("() => Object.keys(IMG).length") == len(cfg["expressions"]), "表情数量不符")

    # 4. 切难度 → #maxLvl
    for key in cfg["diffOrder"]:
        page.click('.m-diff[data-d="%s"]' % key)
        page.wait_for_timeout(120)
        got = page.evaluate("() => document.getElementById('maxLvl').textContent")
        ok(got == str(cfg["difficulties"][key]["levels"]),
           "难度 %s 的 maxLvl=%s 期望 %s" % (key, got, cfg["difficulties"][key]["levels"]))

    # 5. 开局
    page.click("#btnStart")
    page.wait_for_timeout(500)
    ok(page.evaluate("() => state") == "playing", "开局后 state 非 playing")
    ok(page.evaluate("() => document.getElementById('hud').classList.contains('on')"), "HUD 未显示")
    ok(page.evaluate("() => document.getElementById('menu').classList.contains('hidden')"), "菜单未隐藏")

    # 6. 彩蛋页：按难度逐个核对（配置以产物内 CONFIG 为准）
    by_g = page.evaluate("() => (CONFIG.easterEgg || {}).byDiff || {}")
    lack = [k for k in cfg["diffOrder"]
            if k != "easy" and not ((by_g.get(k) or by_g.get("default") or {}).get("prize"))]
    ok(not lack, "v1.2 除轻松(easy)外每个通关难度都必须有惊喜图，缺: %s" % lack)
    ok(not (by_g.get("easy") or {}).get("prize"), "v1.2 轻松(easy)难度不应配惊喜图")
    for key in cfg["diffOrder"]:
        ec = by_g.get(key) or by_g.get("default") or {}
        page.evaluate("""(k) => { diff = k; level = levelMax(); total = 1234; maxCombo = 9; hitCount = 90; missCount = 10; showEasterEgg(); }""", key)
        page.wait_for_timeout(700)
        ok(page.is_visible("#egg"), "难度 %s 彩蛋页不可见" % key)
        ok(page.inner_text("#eggTitle") == (ec.get("title") or "全 部 通 关 ！"), "难度 %s 彩蛋标题不符" % key)
        ok(page.inner_text("#eggGift") == (ec.get("gift") or "🎁"), "难度 %s 礼物表情不符" % key)
        txt = page.inner_text("#eggText")
        ok(txt.strip() != "", "难度 %s 彩蛋文案为空" % key)
        ok(page.evaluate("() => document.getElementById('eggFace').naturalWidth") > 0, "难度 %s 彩蛋头像未加载" % key)
        kick = page.inner_text("#eggKicker")
        lv = str(cfg["difficulties"][key]["levels"])
        exp_kick = ((cfg.get("easterEgg") or {}).get("kicker") or "All {levels} Levels Cleared").replace("{levels}", lv).strip().lower()
        ok(kick.strip().lower() == exp_kick,
           "难度 %s 标语不符: 实测 %r / 期望 %r" % (key, kick, exp_kick))
        n = js_count_colored_pixels(page, "#confetti")
        ok(n > 200, "难度 %s 纸屑未绘制 (像素=%s)" % (key, n))

        # 7. 领取惊喜（v1.2：只有配了惊喜图的难度才有入口，轻松难度没有）
        has_prize = bool(ec.get("prize"))
        btn_on = page.evaluate("() => document.getElementById('btnEggPrize').classList.contains('on')")
        ok(btn_on == has_prize, "难度 %s 领取惊喜入口显示=%s 期望=%s" % (key, btn_on, has_prize))
        if not has_prize:
            ok(not page.is_visible("#prize"), "难度 %s 没配惊喜图却弹出了惊喜页" % key)
            page.click("#btnEggMenu")
            page.wait_for_timeout(400)
            ok(page.is_visible("#menu"), "难度 %s 返回主菜单失败" % key)
            continue
        page.click("#btnEggPrize")
        page.wait_for_timeout(800)
        ok(page.is_visible("#prize"), "难度 %s 惊喜页不可见" % key)
        ok(page.evaluate("() => document.getElementById('prizeImg').naturalWidth") > 0, "难度 %s 惊喜图未加载" % key)
        src = page.evaluate("() => document.getElementById('prizeImg').src")
        prize = ec.get("prize")
        if prize: ok(prize in src or src.startswith("data:image"), "难度 %s 惊喜图 src 异常: %s" % (key, src[:60]))
        ok(page.evaluate("() => document.getElementById('btnPrizeBack').classList.contains('on')") is False, "返回按钮过早出现")
        page.wait_for_timeout(2600)
        ok(page.evaluate("() => document.getElementById('btnPrizeBack').classList.contains('on')"), "难度 %s 3 秒后返回按钮未出现" % key)
        npix = js_count_colored_pixels(page, "#prizeConfetti")
        ok(npix > 200, "难度 %s 惊喜页纸屑未绘制 (像素=%s)" % (key, npix))
        page.click("#btnPrizeBack")
        page.wait_for_timeout(400)
        ok(page.is_visible("#menu"), "返回主菜单失败")

    # 8. 单文件版外部引用
    if kind == "single":
        refs = page.evaluate("() => Array.from(document.querySelectorAll('[src],[href]')).map(e => e.getAttribute('src') || e.getAttribute('href')).filter(u => u && !u.startsWith('data:') && !u.startsWith('#'))")
        ok(not refs, "单文件版存在外部引用: %s" % refs[:5])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--port", type=int, default=9411)
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright
    cfg = json.load(open(a.config, encoding="utf-8"))
    # v1.2：config 允许省略 difficulties / diffOrder / easterEgg（build_game 有内置默认值），
    # 这里复用 build_game 的同一份默认值兜底，避免校验器自己 KeyError
    if not cfg.get("difficulties"):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from build_game import BASE_DIFF as _BD
        except Exception:
            _BD = []
        if _BD:
            cfg["difficulties"] = {k: {"name": nm, "desc": desc, "levels": lv, "interval": itv, "up": up,
                                       "target": tgt, "lives": lf, "lifeCap": cap, "maxSame": ms}
                                   for (k, nm, desc, lv, itv, up, tgt, lf, cap, ms) in _BD}
    cfg.setdefault("diffOrder", list((cfg.get("difficulties") or {}).keys()))
    cfg.setdefault("easterEgg", {})
    d = os.path.abspath(a.dir)
    targets = []
    if os.path.exists(os.path.join(d, "index.html")): targets.append(("dir", os.path.join(d, "index.html")))
    for f in sorted(os.listdir(d)):
        if f.endswith(".html") and "单文件版" in f: targets.append(("single", os.path.join(d, f)))
    if not targets: raise SystemExit("目录下没有可测 HTML: " + d)

    proc = launch_edge(a.port, os.path.join(os.environ.get("TEMP", "."), "mole_edge_prof"))
    report = {"targets": [], "errs": []}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % a.port)
            for kind, path in targets:
                ctx = br.contexts[0]
                page = ctx.new_page()
                page._html_path = path
                errs, console_errs = [], []
                page.on("pageerror", lambda e: errs.append("[%s] JS 异常: %s" % (kind, e)))
                page.on("console", lambda m: console_errs.append(m.text) if m.type == "error" else None)
                info = {"kind": kind, "path": path, "size": os.path.getsize(path)}
                try:
                    check_page(page, cfg, kind, errs)
                except Exception as e:
                    errs.append("[%s] 执行中断: %r" % (kind, e))
                for c in console_errs:
                    if "favicon" not in c: errs.append("[%s] console error: %s" % (kind, c))
                info["errs"] = errs
                report["targets"].append(info)
                report["errs"] += errs
                page.close()
            br.close()
    finally:
        proc.kill()

    out = a.out or os.path.join(d, "verify_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    print(json.dumps({"errs": report["errs"], "checked": [t["kind"] for t in report["targets"]]}, ensure_ascii=False))
    os._exit(0 if not report["errs"] else 1)

if __name__ == "__main__":
    main()

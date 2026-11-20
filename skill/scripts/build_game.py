# -*- coding: utf-8 -*-
"""build_game.py — 用 config.json + 素材生成打地鼠游戏（目录版 / 单文件版）

用法:
  python build_game.py --config config.json --out out/                 # 目录版（含 assets/）
  python build_game.py --config config.json --out out/ --single        # 目录版 + 单文件版
  python build_game.py --config config.json --out out/ --only-single   # 只出单文件

约定:
  - 素材目录默认取 config.json 所在目录，或 --assets 指定；图片文件名来自 config.expressions 与 easterEgg.*.prize
  - 单文件版把上述图片全部内嵌为 data URI，产物无任何外部引用
  - 模板取自本脚本同级 ../assets/game_template.html
"""
import argparse, base64, json, os, shutil, sys, hashlib, mimetypes

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "game_template.html")
PLACEHOLDER = "__MOLE_CONFIG__"
INLINE_LINE = "const INLINE = {};                     // 单文件版会注入 data URI；目录版留空走 assets/"

BASE_DIFF = [
    ("easy",   "轻松", "慢慢冒头", 9,  1050, 1550, 260,  15, None, 1),
    ("normal", "普通", "常规节奏", 9,  810,  1150, 450,  10, 20,   2),
    ("hard",   "困难", "快速连冒", 12, 600,  900,  700,  8,  12,   3),
    ("hell",   "地狱", "手速考验", 15, 420,  700,  1000, 6,  10,   4),
]

NON_EASY_HINT = "除轻松(easy)外的每个难度通关后都必须有惊喜图"

def die(msg):
    print("[ERROR] " + msg); sys.exit(1)

def load_template():
    if not os.path.exists(TEMPLATE): die("模板不存在: " + TEMPLATE)
    return open(TEMPLATE, encoding="utf-8").read()

def default_groups(keys):
    """按命名约定推导三组表情；不匹配则按顺序兜底切分"""
    rise = [k for k in keys if any(t in k.lower() for t in ("smug", "tongue", "tease", "taunt", "disdain", "normal"))]
    hurt = [k for k in keys if any(t in k.lower() for t in ("angry", "cry", "dizzy", "sad", "hurt", "pain"))]
    mock = [k for k in keys if any(t in k.lower() for t in ("taunt", "disdain", "tongue"))]
    if not rise: rise = keys[:max(1, len(keys) * 2 // 3)]
    if not hurt: hurt = keys[max(1, len(keys) * 2 // 3):] or keys[-1:]
    if not mock: mock = rise[-1:]
    return {"rise": rise, "hurt": hurt, "mock": mock}

def normalize(cfg, gate=None):
    cfg = dict(cfg or {})
    exp = cfg.get("expressions") or {}
    if not isinstance(exp, dict) or not exp: die("config.expressions 必须是非空对象 {key: 文件名}")
    for k, v in exp.items():
        if not isinstance(v, str) or not v: die("expressions['%s'] 必须是文件名" % k)
    if len(exp) < 6:
        print("[WARN] 表情数量 %d 偏少，建议 >= 8 张（钻洞 6 张 + 挨打 4 张更好看）" % len(exp))

    g = cfg.get("groups") or {}
    auto = default_groups(list(exp.keys()))
    groups = {}
    for name in ("rise", "hurt", "mock"):
        arr = [k for k in (g.get(name) or auto[name]) if k in exp]
        if not arr: die("groups.%s 为空且无法自动推导" % name)
        groups[name] = arr
    cfg["groups"] = groups

    diffs = cfg.get("difficulties")
    if not diffs:
        diffs = {}
        for key, nm, desc, lv, itv, up, tgt, lf, cap, ms in BASE_DIFF:
            diffs[key] = {"name": nm, "desc": desc, "levels": lv, "interval": itv, "up": up,
                          "target": tgt, "lives": lf, "lifeCap": cap, "maxSame": ms}
        cfg["difficulties"] = diffs
        print("[INFO] 未提供 difficulties，使用内置四档默认值")
    for k, d in cfg["difficulties"].items():
        for f in ("levels", "interval", "up", "target", "lives", "maxSame"):
            if not isinstance(d.get(f), (int, float)): die("difficulties.%s.%s 必须是数字" % (k, f))
        if d["levels"] < 1: die("difficulties.%s.levels 必须 >= 1" % k)
        d.setdefault("name", k); d.setdefault("desc", "")
    cfg.setdefault("diffOrder", list(cfg["difficulties"].keys()))
    cfg.setdefault("defaultDiff", cfg["diffOrder"][0])
    if cfg["defaultDiff"] not in cfg["difficulties"]: die("defaultDiff 不在 difficulties 中")

    rw = cfg.get("rewards") or {}
    rw.setdefault("goldEgg", {}); rw.setdefault("colorEgg", {})
    cfg["rewards"] = rw

    cfg.setdefault("assetDir", "assets/")
    if not cfg["assetDir"].endswith("/"): cfg["assetDir"] += "/"
    cfg.setdefault("title", "打地鼠"); cfg.setdefault("subtitle", ""); cfg.setdefault("kicker", ""); cfg.setdefault("lead", "")
    cfg.setdefault("version", "v1.0.0")
    cfg.setdefault("deco", list(exp.keys())[:9])

    ee = cfg.get("easterEgg") or {}
    by = dict(ee.get("byDiff") or {})
    base = {"gift": "🎁", "title": "全 部 通 关 ！", "text": "打通全部关卡，厉害！",
            "face": list(exp.keys())[0], "prize": None}
    if by.get("default"):
        base = dict(base, **by["default"])
    elif not by:
        by = {"default": dict(base)}
    else:
        by.setdefault("default", dict(base))

    # ---- v1.2：惊喜图必须覆盖"除轻松(easy)外的每个难度"，覆盖方式由用户在门禁里定 ----
    non_easy = [k for k in cfg["diffOrder"] if k != "easy"]
    pz_gate = (gate or {}).get("prize") or {}
    scope = pz_gate.get("scope") or ""
    pmap = pz_gate.get("map") or {}
    same_pick = pz_gate.get("pick") or ""

    def easy_placeholder():
        """轻松难度按设计没有惊喜图：保留它的文案，但显式清空 prize，
           避免 v1.1 的 default 回落把别难度的图塞给轻松难度"""
        it = dict(base)
        it.update(by.get("easy") or {})
        it["prize"] = None
        return it

    if scope == "per_diff":
        for k in non_easy:
            item = dict(base)
            item.update(by.get(k) or {})
            p = pmap.get(k)
            if not p:
                die("%s —— 但 gate.json 里难度 %s 没有定案图，先跑 gen_prize.py --diff %s 再重试"
                    % (NON_EASY_HINT, k, k))
            item["prize"] = os.path.basename(p)
            by[k] = item
        by["easy"] = easy_placeholder()
        by.pop("default", None)
        ee["scope"] = "per_diff"
    elif scope == "same":
        pn = os.path.basename(same_pick) if same_pick else (by["default"].get("prize") or "")
        if not pn:
            die("%s —— 用户选的是全难度共用一张，但 gate.json 的 prize.pick 是空的" % NON_EASY_HINT)
        by["default"] = dict(by["default"], prize=pn)
        for k in non_easy:
            if k in by:
                by[k] = dict(by[k], prize=pn)
        by["easy"] = easy_placeholder()
        ee["scope"] = "same"
    else:
        print("[WARN] 门禁里没有惊喜图覆盖范围（scope）—— v1.2 起必须先问用户："
              "全难度共用一张，还是每个难度各一张")

    def _item(d):
        return by.get(d) or by.get("default") or base

    lack = [k for k in non_easy if not (_item(k) or {}).get("prize")]
    if lack:
        msg = "%s，但这些难度目前没有惊喜图：%s" % (NON_EASY_HINT, "、".join(lack))
        if scope:
            die(msg)
        print("[WARN] " + msg)

    ee["byDiff"] = by
    cfg["easterEgg"] = ee
    return cfg

def collect_images(cfg):
    """返回需要打包/校验的图片名列表（表情 + 惊喜图），去重保序"""
    names = list(dict.fromkeys(list(cfg["expressions"].values())))
    for _, c in cfg["easterEgg"]["byDiff"].items():
        if c.get("prize"): names.append(os.path.basename(str(c["prize"])))
    return list(dict.fromkeys(names))

def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))

def key_for(cfg, filename):
    """表情 key：优先用 expressions 的 key 作为内嵌键；惊喜图直接用文件名作为键"""
    for k, v in cfg["expressions"].items():
        if v == filename: return k
    return filename

GATE_ITEMS = [("photo", "照片来源（谁给的图）"),
              ("expressions", "表情小样三选一确认"),
              ("prize", "惊喜图来源与文字确认"),
              ("identity", "真人特征分析与卡通相似度确认（v1.3）")]

IDENTITY_FAIL_SCORE = 65


def gate_check(cfg_path, gate_path, allow_no_gate):
    """v1.1 硬门禁：没走完四道确认就不许出游戏（v1.3 增加身份一致性门禁）。"""
    p = gate_path
    if not p:
        d0 = os.path.dirname(cfg_path)
        for cand in (os.path.join(d0, "gate.json"), os.path.join(os.path.dirname(d0), "gate.json")):
            if os.path.exists(cand):
                p = cand
                break
    if not p or not os.path.exists(p):
        msg = ("未找到 gate.json，说明照片 / 表情小样 / 惊喜图 / 卡通相似度这几关还没跟用户确认过。\n"
               "  正确做法：先用 gate.py 逐项写入用户确认（--photo / --expressions / --prize / "
               "--identity-*），再回来构建。\n  仅调试模板时可加 --allow-no-gate 跳过。")
        if allow_no_gate:
            print("  [警告] 已跳过门禁（--allow-no-gate）：%s" % msg.replace("\n", " "))
            return None
        die(msg)
    try:
        g = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        die("gate.json 无法解析（%r），请重新用 gate.py 写入。" % e)
    missing = [cn for k, cn in GATE_ITEMS if not (g.get(k) or {}).get("confirmed")]
    if missing and not allow_no_gate:
        die("门禁未通过，还缺：%s\n  文件：%s\n  用 gate.py --show 查看当前状态，补齐后再构建。"
            % ("、".join(missing), p))
    idf = g.get("identity") or {}
    if idf.get("confirmed") and not allow_no_gate:
        sc = idf.get("score")
        if not isinstance(sc, int) or sc < IDENTITY_FAIL_SCORE:
            die("身份门禁登记的相似度评分无效（%r）：%s\n"
                "  v1.3 要求卡通形象与真人原图对照评分 ≥ %d 分才能构建。"
                "请回阶段 A0 按差异点重做，不要绕过门禁直接构建。"
                % (sc, "低于放行线" if isinstance(sc, int) else "缺失", IDENTITY_FAIL_SCORE))
        if not idf.get("compare") or not os.path.exists(idf.get("compare")):
            die("身份门禁登记的原图/卡通对照图不存在：%r\n"
                "  请用 identity.py --compare-sheet 重新生成对照图并重写门禁。" % idf.get("compare"))
        ftr = idf.get("features")
        if not ftr or not os.path.exists(ftr):
            die("身份门禁登记的真人特征 JSON 不存在：%r\n"
                "  相似度必须建立在特征分析之上，请补齐特征 JSON。" % ftr)
    print("  [门禁] 通过 %s（%d/%d 项已确认）"
          % (os.path.basename(p), len(GATE_ITEMS) - len(missing), len(GATE_ITEMS)))
    for k, _cn in GATE_ITEMS:
        it = g.get(k) or {}
        if it.get("confirmed"):
            extra = ""
            if k == "identity":
                extra = "  [相似度 %s 分 / %s]" % (it.get("score"), it.get("status"))
            print("         · %-11s 用户原话：%s%s" % (k, it.get("quote", ""), extra))
    return g


def cutout_report_check(asset_dir, allow_no_gate):
    """v1.3 硬门禁：assets/cutout.report.json 必须存在且无 FAIL（红线 5：抠后必须比对）。"""
    rp = os.path.join(asset_dir, "cutout.report.json")
    if not os.path.exists(rp):
        msg = ("未找到 %s，说明阶段 B 的「抠后比对」没做（cutout.py --verify）。\n"
               "  抠图没验就构造，等于把阶段 B 白做，交付后用户第一眼就会看到\"人少了半个\"。\n"
               "  正确做法：cutout.py --in raw/ --out assets/ --normalize --chroma auto "
               "--verify --compare，看 cutout.report.json 全 PASS 再回来构建。\n"
               "  仅调试模板时可加 --allow-no-gate 跳过。" % rp)
        if allow_no_gate:
            print("  [警告] 已跳过抠图报告校验（--allow-no-gate）")
            return None
        die(msg)
    try:
        rep = json.load(open(rp, encoding="utf-8"))
    except Exception as e:
        die("cutout.report.json 无法解析（%r），请重跑 cutout.py --verify。" % e)
    sm = rep.get("summary") or {}
    nfail = sm.get("fail") or 0
    if not isinstance(nfail, int):
        nfail = len(nfail or [])
    rework = sm.get("rework") or []
    warn_keys = sm.get("warn_keys") or []
    if nfail and not allow_no_gate:
        die("抠图报告存在 FAIL %d 张：%s\n  按红线 5，抠图不许吞掉主体/衣服/配件。"
            "请回阶段 A 换背景色重生这几张，再重新 --analyze → 抠图 → --verify，"
            "不要在这里硬调 --tol。\n  报告：%s"
            % (nfail, ", ".join(rework) if rework else "(见报告)", rp))
    print("  [抠图] 报告 %s：PASS %s / WARN %s / FAIL %s"
          % (os.path.basename(rp), sm.get("pass", "?"), sm.get("warn", "?"), sm.get("fail", "?")))
    if warn_keys:
        print("         · WARN 待目视核对：%s" % ", ".join(warn_keys))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--assets", default=None, help="素材目录，默认 config 所在目录")
    ap.add_argument("--single", action="store_true", help="同时输出单文件版")
    ap.add_argument("--only-single", action="store_true", help="只输出单文件版")
    ap.add_argument("--gate", default=None, help="门禁文件，默认在 config 同级/上级找 gate.json")
    ap.add_argument("--allow-no-gate", action="store_true", help="仅调试模板时跳过门禁校验")
    a = ap.parse_args()

    cfg_path = os.path.abspath(a.config)
    g = gate_check(cfg_path, a.gate, a.allow_no_gate)
    cfg = normalize(json.load(open(cfg_path, encoding="utf-8")), gate=g)
    asset_dir = os.path.abspath(a.assets or os.path.dirname(cfg_path))
    cutout_report_check(asset_dir, a.allow_no_gate)
    out_dir = os.path.abspath(a.out)
    os.makedirs(out_dir, exist_ok=True)

    imgs = collect_images(cfg)
    missing = [n for n in imgs if not os.path.exists(os.path.join(asset_dir, n))]
    if missing:
        die("素材缺失（在 %s 下找不到）: %s" % (asset_dir, ", ".join(missing)))
    for k, v in cfg["expressions"].items():
        if v not in imgs: imgs.append(v)

    tpl = load_template()
    assert tpl.count(PLACEHOLDER) == 1, "模板 CONFIG 占位符异常"
    assert tpl.count(INLINE_LINE) == 1, "模板 INLINE 定义行异常（v1.4 模板被改动？）"

    cfg_json = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
    # 防 </script> 截断；同时避免 JSON 里的 </ 造成解析歧义
    cfg_json = cfg_json.replace("</", "<\\/")

    title = cfg["title"]
    results = []

    # ---------- 目录版 ----------
    if not a.only_single:
        html = tpl.replace(PLACEHOLDER, cfg_json)
        d = os.path.join(out_dir, "index.html")
        open(d, "w", encoding="utf-8", newline="\n").write(html)
        ad = os.path.join(out_dir, cfg["assetDir"].strip("/"))
        os.makedirs(ad, exist_ok=True)
        for n in imgs:
            shutil.copy2(os.path.join(asset_dir, n), os.path.join(ad, n))
        results.append(("目录版", d, os.path.getsize(d)))

    # ---------- 单文件版 ----------
    if a.single or a.only_single:
        inline = {key_for(cfg, n): data_uri(os.path.join(asset_dir, n)) for n in imgs}
        inline_json = json.dumps(inline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        html = tpl.replace(PLACEHOLDER, cfg_json).replace(
            INLINE_LINE, "const INLINE = " + inline_json + ";   // 单文件版：全部素材内嵌")
        assert PLACEHOLDER not in html, "单文件版仍残留 CONFIG 占位符"
        d = os.path.join(out_dir, "%s_单文件版_%s.html" % (title, cfg["version"]))
        open(d, "w", encoding="utf-8", newline="\n").write(html)
        results.append(("单文件版", d, os.path.getsize(d)))

    # ---------- 校验报告 ----------
    for kind, path, size in results:
        h = hashlib.sha256(open(path, "rb").read()).hexdigest().upper()
        txt = open(path, encoding="utf-8").read()
        ext_refs = txt.count('src="assets/') + txt.count("src='assets/")
        print("%-6s %s" % (kind, path))
        print("       字节=%d  SHA256=%s  静态外部引用=%d  表情=%d  难度=%s"
              % (size, h, ext_refs, len(cfg["expressions"]), "/".join(
                  "%s:%s关" % (cfg["difficulties"][k].get("name", k), cfg["difficulties"][k]["levels"]) for k in cfg["diffOrder"])))
        byd = cfg["easterEgg"]["byDiff"]
        pz = []
        for k in cfg["diffOrder"]:
            it = byd.get(k) or byd.get("default") or {}
            pz.append("%s=%s" % (k, it.get("prize") or "无"))
        print("       惊喜图覆盖 %s（用户选：%s）"
              % (" / ".join(pz), cfg["easterEgg"].get("scope") or "未记录"))

if __name__ == "__main__":
    main()

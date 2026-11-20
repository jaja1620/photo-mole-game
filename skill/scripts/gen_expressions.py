# -*- coding: utf-8 -*-
"""gen_expressions.py — 批量生成「照片→卡通表情包」的调度脚本

三条路线（按可用性选择，脚本统一产出 raw/ 原图 + manifest.json）:
  A. 本地引擎（推荐，可全自动）: --endpoint http://127.0.0.1:8790，直接打 sdapi/img2img
  B. MCP 出图（flux.2 等）: 用 --manifest-only 打印每张的 prompt，由 agent 调 locmodel MCP 逐张生成后放回 raw/
  C. 线上/WorkBuddy 技能或工作流: 同样用 --manifest-only 拿 prompt，回传结果放入 raw/

生成完成后统一交给 cutout.py 抠图 + 归一化，再由 build_game.py 打包。

用法示例:
  # 看当前默认 11 个表情与提示词（不生成）
  python gen_expressions.py --photo me.jpg --list

  # 本地批量生成（照片直接 img2img）
  python gen_expressions.py --photo me.jpg --out raw/ --endpoint http://127.0.0.1:8790 \
      --desc "cute young woman with short hair and glasses" --strength 0.66 --count-each 1

  # 只有 3 张要改（客户选定修改 + 补充要求）
  python gen_expressions.py --photo me.jpg --out raw/ --only 05_angry,06_cry,07_dizzy \
      --extra-prompt "eyes bigger, hair tied up" --seed 20261112

  # 先出定妆照，再以定妆照为基准扩表情（一致性更高）
  python gen_expressions.py --photo me.jpg --out raw/ --endpoint ... --two-stage
"""
import argparse, base64, json, os, sys, time
import urllib.request, urllib.error

# 默认 11 表情：key = 文件名主干，value = 英文表情描述（用于拼 prompt）+ 中文名（给用户看）
EXPRESSIONS = [
    ("normal",        "gentle neutral smile, calm eyes",                      "标准微笑"),
    ("01_smug",       "smug confident smirk, one eyebrow raised",              "得意坏笑"),
    ("02_tongue",     "playful tongue sticking out, winking",                  "吐舌眨眼"),
    ("03_tease",      "teasing grin, squinting eyes, cheeky look",             "挑衅坏笑"),
    ("04_taunt",      "cocky taunt expression, chin up, half-lidded eyes",     "嚣张挑逗"),
    ("05_angry",      "angry pouting face, eyebrows furrowed, cheeks puffed",  "生气嘟嘴"),
    ("06_cry",        "crying face, big teardrops, trembling mouth",           "哇哇大哭"),
    ("07_dizzy",      "dizzy stunned face, spiral eyes, mouth open in a daze", "被打懵/晕"),
    ("08_surprised",  "surprised face, wide eyes, mouth open in shock",        "吃惊"),
    ("09_disdain",    "disdainful side-eye, cold contemptuous look",           "鄙视白眼"),
    ("10_sad",        "sad dejected face, drooping eyes, frown",               "委屈难过"),
]

# v1.2：小样背景一律用「利于后期抠图」的纯色（色度键 / chroma key）。
# 理由：渐变、浅色几何、场景背景都会让 cutout.py 的 GrabCut 判错边缘（白衣服被当背景删掉）。
# 纯色背景 + 固定色值写进 manifest，cutout.py --chroma auto 直接读色值一键抠净。
BG_PRESETS = {
    "magenta": ("#FF00FF", "solid flat pure magenta", "品红（默认，与肤色/衣服色差最大）"),
    "green":   ("#00FF00", "solid flat pure chroma-key green", "纯绿（人物穿红/紫时换它）"),
    "blue":    ("#0000FF", "solid flat pure blue", "纯蓝（人物穿绿时换它）"),
    "white":   ("#FFFFFF", "solid flat pure white", "纯白（人物有深色描边时可用）"),
}

PROMPT_POS = ("chibi anime cartoon portrait of {desc}, {expr}, upper body head and shoulders, "
              "facing viewer, centered, {style}, thick clean outline, soft cel shading, "
              "{bg} background ({bg_hex}), completely uniform fill, no gradient, no vignette, "
              "no shadow, no props, high quality, sharp focus")
PROMPT_NEG = ("photorealistic, photo, realistic skin texture, blurry, lowres, jpeg artifacts, "
              "deformed face, asymmetric eyes, distorted mouth, extra fingers, bad hands, "
              "text, watermark, signature, multiple people, cropped head, "
              "gradient background, textured background, patterned wall, scenery, landscape, "
              "bokeh, room interior, drop shadow, cast shadow, props, furniture, "
              "3d render, plastic doll")
STYLE_DEFAULT = "kawaii flat illustration style, 2d anime, vivid but soft colors"

# v1.3：身份锁定负向词（--features 生效时自动追加）。
# 这四条是「不像本人」的典型成因：换了个人、掉进通用动漫脸、发型跑掉、眼镜丢了、脸型变了。
IDENTITY_NEG = ("different person, generic anime face, wrong hairstyle, missing glasses, "
                "changed face shape, different hair color, unrecognizable identity")


def load_identity(features_path):
    """读 identity.py 的特征 JSON，返回 (desc_en, lock_pos, lock_neg, summary_cn)。
    与 identity.py 共用同一份字段口径，避免两处规则漂移。"""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "identity.py")
    if not os.path.exists(cand):
        raise SystemExit("缺少 scripts/identity.py，无法使用 --features")
    spec = importlib.util.spec_from_file_location("pmg_identity", cand)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = mod.load_features(features_path)
    em = mod.emit(data)
    ok, missing, warns = mod.validate(data)
    return em["desc_en"], em["lock_pos"], em["lock_neg"], em["summary_cn"], ok, missing, warns


def resolve_bg(bg, bg_hex=""):
    """把 --bg / --bg-hex 解析成 (名称, #RRGGBB, 英文描述)。--bg-hex 优先。"""
    if bg_hex.strip():
        h = bg_hex.strip()
        if not h.startswith("#"):
            h = "#" + h
        h = h.upper()
        if len(h) != 7:
            raise SystemExit("--bg-hex 需 #RRGGBB 形式，收到: %s" % bg_hex)
        nm = next((k for k, v in BG_PRESETS.items() if v[0] == h), "custom")
        d = BG_PRESETS[nm][1] if nm != "custom" else "solid flat pure color"
        return nm, h, d
    if bg not in BG_PRESETS:
        raise SystemExit("--bg 只支持 %s；要自定义请用 --bg-hex #RRGGBB" % " / ".join(BG_PRESETS))
    hx, d, _cn = BG_PRESETS[bg]
    return bg, hx, d


def build_prompt(desc, expr, style, extra="", bg="magenta", bg_hex="", lock_pos=""):
    _nm, hx, d = resolve_bg(bg, bg_hex)
    p = PROMPT_POS.format(desc=desc, expr=expr, style=style, bg=d, bg_hex=hx)
    if lock_pos.strip():
        p += ", " + lock_pos.strip()
    if extra.strip():
        p += ", " + extra.strip()
    return p


def build_negative(lock_neg=""):
    neg = PROMPT_NEG
    if lock_neg.strip():
        neg = neg + ", " + lock_neg.strip()
    return neg


def http_json(url, payload, timeout=600):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def probe(endpoint):
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/sdapi/v1/options", timeout=5) as r:
            r.read(200)
        return True
    except Exception:
        return False


def img2img(endpoint, init_b64, prompt, neg, strength, steps, sampler, cfg, seed, w, h):
    payload = {
        "init_images": [init_b64], "prompt": prompt, "negative_prompt": neg,
        "denoising_strength": strength, "steps": steps, "sampler_name": sampler,
        "cfg_scale": cfg, "seed": seed, "width": w, "height": h,
        "batch_size": 1, "n_iter": 1, "save_images": False,
    }
    res = http_json(endpoint.rstrip("/") + "/sdapi/v1/img2img", payload)
    if "images" not in res or not res["images"]:
        raise RuntimeError("引擎未返回图片")
    return res["images"][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", required=True, help="用户上传的照片（正面清晰人像最佳）")
    ap.add_argument("--out", default="raw", help="原图输出目录")
    ap.add_argument("--desc", default="", help="人物形象描述（英文最优），用于保证角色一致性")
    ap.add_argument("--features", default="",
                    help="[v1.3] 真人面部特征 JSON（identity.py --template 产出）：自动写入 desc + 身份锁定"
                         "正向词，负向词追加「不同的人/通用动漫脸/发型不符/缺眼镜/脸型改变」")
    ap.add_argument("--style", default=STYLE_DEFAULT, help="画风描述")
    ap.add_argument("--extra-prompt", default="", help="客户追加的修改要求")
    ap.add_argument("--endpoint", default="", help="sd-server 地址，如 http://127.0.0.1:8790；留空则只导出 prompt 清单")
    ap.add_argument("--only", default="", help="只生成/重做这几个 key（逗号分隔），如 05_angry,06_cry")
    ap.add_argument("--seed", type=int, default=20261112, help="基准种子；每张 = seed + idx*13")
    ap.add_argument("--strength", type=float, default=0.66, help="img2img 强度（0.55~0.75 常用）")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--sampler", default="euler")
    ap.add_argument("--cfg", type=float, default=7.0)
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=1024)
    ap.add_argument("--count-each", type=int, default=1, help="每个表情出几张候选（1~3）")
    ap.add_argument("--two-stage", action="store_true", help="先出定妆照 base.png，再以它为基准扩表情")
    ap.add_argument("--bg", default="magenta", choices=list(BG_PRESETS.keys()),
                    help="小样背景色（利于抠图的纯色，默认 magenta）")
    ap.add_argument("--bg-hex", default="", help="自定义背景色 #RRGGBB，覆盖 --bg")
    ap.add_argument("--list", action="store_true", help="只列出表情清单与 prompt")
    ap.add_argument("--manifest-only", action="store_true", help="只导出 manifest.json（供 MCP/线上模型执行）")
    a = ap.parse_args()

    bg_name, bg_hex, bg_desc = resolve_bg(a.bg, a.bg_hex)

    picked = EXPRESSIONS
    if a.only:
        want = [x.strip() for x in a.only.split(",") if x.strip()]
        picked = [e for e in EXPRESSIONS if e[0] in want]
        missing = [w for w in want if w not in [e[0] for e in EXPRESSIONS]]
        if missing: print("  [警告] 未知表情 key 已忽略: %s" % missing)
        if not picked: raise SystemExit("--only 未匹配到任何表情")

    desc = a.desc.strip() or "the uploaded person, keep facial features and hairstyle recognizable"

    # v1.3：--features 生效 → desc 与身份锁定词由真人特征 JSON 驱动，不再靠手写一句话
    lock_pos, lock_neg, identity_meta = "", "", None
    if a.features.strip():
        f_desc, lock_pos, lock_neg, summary_cn, ok, missing, warns = load_identity(a.features)
        desc = f_desc or desc
        identity_meta = {"features": os.path.abspath(a.features), "desc": f_desc,
                         "lock_pos": lock_pos, "lock_neg": lock_neg,
                         "summary_cn": summary_cn, "validate_ok": bool(ok),
                         "missing": missing, "warnings": warns}
        print("[v1.3] 已载入真人特征: %s" % os.path.abspath(a.features))
        print("  特征摘要: %s" % (summary_cn or "(空)"))
        if not ok:
            print("  [警告] 特征必填缺 %d 项：%s —— 建议先补再出图，否则容易不像本人"
                  % (len(missing), ", ".join(missing)))
        for w in warns:
            print("  [建议] %s" % w)
        print("  身份锁定词: %s" % lock_pos)

    neg = build_negative(lock_neg)
    tasks = []
    for idx, (key, expr, cn) in enumerate(EXPRESSIONS):
        tasks.append({"key": key, "cn": cn, "expression": expr, "seed": a.seed + idx * 13,
                      "prompt": build_prompt(desc, expr, a.style, a.extra_prompt, bg_name, bg_hex,
                                             lock_pos),
                      "negative_prompt": neg, "bg_hex": bg_hex, "file": key + ".png"})
    sel = [t for t in tasks if t in tasks and t["key"] in [p[0] for p in picked]]

    if a.list:
        print("背景色: %s %s —— %s" % (bg_name.upper(), bg_hex, bg_desc))
        print("（纯色背景是抠图前提；小样确认时可用 make_sheet.py --check-bg 验收）\n")
        print("共 %d 个表情：\n" % len(EXPRESSIONS))
        for t in tasks:
            mark = "*" if t in sel else " "
            print("%s %-14s %-10s seed=%-10d\n    %s\n" % (mark, t["key"], t["cn"], t["seed"], t["prompt"]))
        return

    os.makedirs(a.out, exist_ok=True)
    man_path = os.path.join(a.out, "manifest.json")
    manifest = {"photo": os.path.abspath(a.photo), "desc": desc, "style": a.style,
                "bg": {"name": bg_name, "hex": bg_hex},
                "extra_prompt": a.extra_prompt, "mode": "pending", "items": []}
    if identity_meta:
        manifest["identity"] = identity_meta
        manifest["version"] = "1.3.0"

    if a.manifest_only or not a.endpoint:
        for t in sel:
            manifest["items"].append({**t, "status": "pending",
                                      "hint": "用 locmodel MCP(generate_image/redraw_image) 或线上图片转卡通 skill 按此 prompt 生成，另存为 " + t["file"]})
        manifest["mode"] = "external"
        json.dump(manifest, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("已导出 prompt 清单: %s（%d 张待生成）" % (man_path, len(sel)))
        print("路线提示: locmodel MCP → redraw_image(init_image=用户照片, prompt=清单内 prompt, strength=%.2f, seed=清单内 seed)" % a.strength)
        return

    if not probe(a.endpoint):
        raise SystemExit("引擎不可达: %s。请先启动本地 LocModel/sd-server，或改用 --manifest-only 走 MCP/线上路线。" % a.endpoint)

    photo_b64 = base64.b64encode(open(a.photo, "rb").read()).decode()
    base_b64 = photo_b64
    if a.two_stage and not a.only:
        print("[1/2] 生成定妆照 base.png ...")
        try:
            img_b64 = img2img(a.endpoint, photo_b64,
                              build_prompt(desc, EXPRESSIONS[0][1], a.style, "", bg_name, bg_hex,
                                           lock_pos),
                              neg, a.strength, a.steps, a.sampler, a.cfg, a.seed, a.width, a.height)
            bp = os.path.join(a.out, "base.png")
            open(bp, "wb").write(base64.b64decode(img_b64))
            base_b64 = img_b64
            print("    -> %s" % bp)
        except Exception as e:
            print("    [警告] 定妆照失败，回落为照片直出: %r" % e)

    print("[%d 张] 开始生成 ..." % len(sel))
    for i, t in enumerate(sel, 1):
        for k in range(a.count_each):
            seed = t["seed"] + k * 101
            name = t["file"] if a.count_each == 1 else t["key"] + "_c%d.png" % k
            out = os.path.join(a.out, name)
            t0 = time.time()
            try:
                b64 = img2img(a.endpoint, base_b64, t["prompt"], t["negative_prompt"],
                              a.strength, a.steps, a.sampler, a.cfg, seed, a.width, a.height)
                open(out, "wb").write(base64.b64decode(b64))
                st, msg = "done", "%.0fs" % (time.time() - t0)
                print("  [%d/%d] %-14s seed=%-10d -> %s (%s)" % (i, len(sel), t["key"], seed, name, msg))
            except Exception as e:
                st, msg = "failed", repr(e)
                print("  [%d/%d] %-14s 失败: %s" % (i, len(sel), t["key"], e))
            manifest["items"].append({**t, "seed_used": seed, "status": st, "error": msg if st == "failed" else ""})

    manifest["mode"] = "local"
    manifest["two_stage"] = bool(a.two_stage)
    manifest["strength"] = a.strength
    json.dump(manifest, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    done = sum(1 for x in manifest["items"] if x["status"] == "done")
    print("\n完成 %d / %d，manifest: %s" % (done, len(manifest["items"]), man_path))
    print("背景色 %s %s 已写入 manifest，下一句务必带 --chroma auto 再抠图：" % (bg_name, bg_hex))
    print("  python {baseDir}/scripts/cutout.py --in %s --out assets/ --normalize --chroma auto" % a.out)


if __name__ == "__main__":
    main()

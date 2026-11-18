# -*- coding: utf-8 -*-
"""
gen_prize.py — 惊喜图生成（v1.1 新增，v1.2 重做：分难度 + 三种来源 + 候选合成）

惊喜图 = 通关后彩蛋页里出现的那张"奖励图"。v1.2 起规则变了，必须先问用户三件事
（都通过 gate.py --prize 留痕），再来跑本脚本：

  问题 1：惊喜图是「你上传的图」还是「系统自动生成」？
  问题 2：除轻松(easy)外的每个难度通关都要有惊喜图；那是全难度**共用同一张**，
          还是**每个难度各一张不同图**？（--scope same / per_diff）
  问题 3：图上要不要写字？文字你给，还是我按主题自动想一句？

三种取图路线（--mode）：
  ai      —— 本地引擎 img2img 出全身卡通多姿势（本机 LocModel/sd-server 可用时）
  user    —— 用户直接给的图，按难度归位入库
  compose —— 纯 Pillow 本地合成"通关奖励"样式，一次出 3 个版式候选（最快、离线、零成本）

文件名约定（v1.2）：
  共用：prize.jpg（定案） / prize_<tag>.png（暂存）
  分难度：prize_<diff>.jpg / prize_<diff>_<tag>.png
  build_game.py 按 config 的 easterEgg.byDiff[难度].prize 去 assets 里取。

用法：
  # A. 全难度共用 + 用户上传
  python {baseDir}/scripts/gen_prize.py --mode user --input "D:/照片/gift.jpg" --out work/敲小人/prize --text "生日快乐"

  # B. 分难度各一张（normal/hard/hell 各出 3 个姿势候选）
  python {baseDir}/scripts/gen_prize.py --mode ai --init work/敲小人/assets/normal.png \
      --per-diff normal,hard,hell --out work/敲小人/prize --text-map "normal:不错嘛;hard:厉害;hell:你是神吗"

  # C. 本地合成 3 个版式候选（不需要引擎）
  python {baseDir}/scripts/gen_prize.py --mode compose --input "D:/照片/gift.jpg" \
      --per-diff normal,hard,hell --out work/敲小人/prize --theme gold

  # D. 候选拼小样给用户挑 → 按难度定案
  python {baseDir}/scripts/make_sheet.py --in work/敲小人/prize --out work/敲小人/prize/sheet_prize.jpg
  python {baseDir}/scripts/gen_prize.py --pick work/敲小人/prize/prize_normal_cand1_card.png --diff normal --out work/敲小人/prize
"""
import argparse
import base64
import json
import os
import random
import shutil
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\Deng.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]

STYLE = ("clean cartoon illustration, bold outlines, flat cel shading, warm friendly palette, "
         "sticker style, high quality, single character")

# key, 中文名, 姿势描述
POSES = [
    ("pose1_wave", "站立挥手", "full body shot from head to toe, standing upright facing viewer, "
                              "one hand raised waving hello, other hand relaxed, big warm smile, "
                              "confetti and floating stars around, generous headroom and feet visible"),
    ("pose2_cheer", "欢呼跳起", "full body shot from head to toe, jumping in the air with both arms up, "
                               "celebrating victory, laughing, motion lines, ribbons and confetti bursting, "
                               "feet off ground but fully inside frame"),
    ("pose3_hip", "叉腰得意", "full body shot from head to toe, standing with hands on hips, "
                             "proud smug grin, chin up, one leg slightly forward, sparkle effects, "
                             "gift box beside the character, feet fully inside frame"),
]
PROMPT_NEG = ("lowres, bad anatomy, bad hands, extra fingers, missing limbs, cropped head, cropped feet, "
              "out of frame, watermark, text, logo, blurry, deformed, multiple views, close-up portrait, "
              "half body only, nsfw")


# ---------------- 引擎调用 ----------------
def http_json(url, payload, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def probe(endpoint):
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/sdapi/v1/options", timeout=5) as r:
            r.read(16)
        return True
    except Exception:
        return False


def img2img(endpoint, init_b64, prompt, neg, strength, steps, sampler, cfg, seed, w, h):
    payload = {"init_images": [init_b64], "prompt": prompt, "negative_prompt": neg,
               "denoising_strength": strength, "steps": steps, "cfg_scale": cfg,
               "sampler_name": sampler, "seed": seed, "width": w, "height": h,
               "resize_mode": 1, "batch_size": 1, "n_iter": 1}
    d = http_json(endpoint.rstrip("/") + "/sdapi/v1/img2img", payload)
    imgs = d.get("images") or []
    if not imgs:
        raise RuntimeError("引擎无返回图像: %r" % (str(d)[:200],))
    return imgs[0].split(",", 1)[-1]


# ---------------- 文字排版 ----------------
def font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_caption(src, dst, text, where="bottom"):
    """在图片外加一条文字卡，避免压到人物。where=bottom/top/none"""
    im = Image.open(src).convert("RGB")
    if not text.strip() or where == "none":
        im.save(dst, quality=92)
        return
    W = im.width
    f = font(max(22, int(W * 0.075)))
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    try:
        tw = tmp.textlength(text, font=f)
    except Exception:
        tw = len(text) * f.size
    while tw > W * 0.9 and f.size > 16:
        f = font(f.size - 2)
        try:
            tw = tmp.textlength(text, font=f)
        except Exception:
            tw = len(text) * f.size
    bar = int(f.size * 2.0)
    out = Image.new("RGB", (W, im.height + bar), (255, 252, 245))
    if where == "top":
        out.paste(im, (0, bar))
    else:
        out.paste(im, (0, 0))
    dr = ImageDraw.Draw(out)
    y = (bar - f.size) // 2 - 2 if where == "top" else im.height + (bar - f.size) // 2 - 2
    dr.text(((W - tw) // 2, y), text, font=f, fill=(212, 78, 60))
    out.save(dst, quality=92)


# ---------------- v1.2：本地合成（把用户照片或卡通像合成一张可用惊喜图） ----------------
import math

LAYOUTS = {
    "card":   "竖版卡片：圆角方图 + 顶部丝带标题",
    "circle": "圆形头像 + 光环放射线 + 底部文字",
    "badge":  "勋章：双环圆章 + 顶部星标",
}
THEMES = {
    "gold":  {"bg": (255, 247, 228), "accent": (214, 154, 46), "deep": (128, 84, 22), "ink": (92, 58, 12)},
    "rose":  {"bg": (255, 239, 243), "accent": (222, 96, 130), "deep": (144, 42, 70), "ink": (110, 32, 58)},
    "mint":  {"bg": (233, 251, 244), "accent": (54, 172, 142), "deep": (18, 96, 80), "ink": (16, 78, 64)},
    "night": {"bg": (32, 38, 60), "accent": (242, 204, 98), "deep": (18, 22, 38), "ink": (250, 244, 222)},
}


def _grad(w, h, c1, c2):
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        t = y / float(max(1, h - 1))
        px[0, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return strip.resize((w, h))


def _confetti(dr, w, h, color, n=32, seed=7, lo=3, hi=10):
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.randint(10, w - 10), rnd.randint(10, h - 10)
        r = rnd.randint(lo, hi)
        dr.ellipse([x - r, y - r, x + r, y + r], fill=color)


def _fit(im, size):
    return ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS, centering=(0.5, 0.42))


def _round_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def _circle_mask(size):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse([0, 0, size[0] - 1, size[1] - 1], fill=255)
    return m


def _center(dr, txt, f, box, color):
    try:
        tw = dr.textlength(txt, font=f)
    except Exception:
        tw = len(txt) * f.size
    x = box[0] + (box[2] - box[0] - tw) // 2
    y = box[1] + (box[3] - box[1] - f.size) // 2 - 2
    dr.text((x, y), txt, font=f, fill=color)


def _wrap(txt, f, maxw, dr):
    lines, cur = [], ""
    for ch in txt:
        t = cur + ch
        try:
            wpx = dr.textlength(t, font=f)
        except Exception:
            wpx = len(t) * f.size
        if wpx > maxw and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def compose(src, dst, text="", theme="gold", layout="card", size=(900, 1200)):
    """把一张图合成成"通关奖励"样式（纯本地 Pillow，不需引擎、不需联网）。
    三种版式 card/circle/badge 供用户挑，用户选定后再 --pick 定案。"""
    th = THEMES.get(theme, THEMES["gold"])
    W, H = size
    im = Image.open(src)
    base = _grad(W, H, th["bg"], tuple(max(0, c - 30) for c in th["bg"]))
    dr = ImageDraw.Draw(base)
    soft = tuple(int(th["bg"][i] * 0.55 + th["accent"][i] * 0.45) for i in range(3))
    _confetti(dr, W, H, soft, n=34, seed=abs(hash(layout)) % 97, lo=3, hi=10)

    pad = int(W * 0.03)
    bw = max(4, int(W * 0.008))
    dr.rounded_rectangle([pad, pad, W - pad, H - pad], radius=int(W * 0.05),
                         outline=th["accent"], width=bw)
    f_label = font(int(W * 0.045))
    f_text = font(int(W * 0.078))

    if layout == "circle":
        d = int(W * 0.72)
        cx, cy = W // 2, int(H * 0.40)
        for k in range(36):
            a = 2 * math.pi * k / 36.0
            r1, r2 = d // 2 + int(W * 0.03), d // 2 + int(W * 0.072)
            dr.line([cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                     cx + r2 * math.cos(a), cy + r2 * math.sin(a)], fill=th["accent"], width=5)
        base.paste(_fit(im, (d, d)), (cx - d // 2, cy - d // 2), _circle_mask((d, d)))
        dr.ellipse([cx - d // 2, cy - d // 2, cx + d // 2, cy + d // 2],
                   outline=th["accent"], width=max(6, int(W * 0.012)))
        dr.ellipse([cx - d // 2 - 16, cy - d // 2 - 16, cx + d // 2 + 16, cy + d // 2 + 16],
                   outline=th["deep"], width=3)
        ty = cy + d // 2 + int(H * 0.045)
    elif layout == "badge":
        d = int(W * 0.64)
        cx, cy = W // 2, int(H * 0.38)
        dr.ellipse([cx - d // 2 - 28, cy - d // 2 - 28, cx + d // 2 + 28, cy + d // 2 + 28],
                   fill=th["accent"])
        dr.ellipse([cx - d // 2 - 12, cy - d // 2 - 12, cx + d // 2 + 12, cy + d // 2 + 12],
                   fill=th["bg"])
        base.paste(_fit(im, (d, d)), (cx - d // 2, cy - d // 2), _circle_mask((d, d)))
        dr.polygon([(W // 2 - int(W * 0.10), int(H * 0.05)), (W // 2 + int(W * 0.10), int(H * 0.05)),
                    (W // 2, int(H * 0.14))], fill=th["accent"])
        _center(dr, "★", font(int(W * 0.05)),
                [W // 2 - 60, int(H * 0.05), W // 2 + 60, int(H * 0.105)], (255, 255, 255))
        ty = cy + d // 2 + int(H * 0.055)
    else:  # card
        pw = int(W * 0.78)
        px, py = (W - pw) // 2, int(H * 0.21)
        base.paste(_fit(im, (pw, pw)), (px, py), _round_mask((pw, pw), int(W * 0.05)))
        dr.rounded_rectangle([px, py, px + pw, py + pw], radius=int(W * 0.05),
                             outline=th["deep"], width=max(4, int(W * 0.007)))
        rb = [int(W * 0.17), int(H * 0.105), int(W * 0.83), int(H * 0.175)]
        dr.rounded_rectangle(rb, radius=int(W * 0.032), fill=th["accent"])
        _center(dr, "通 关 奖 励", f_label, rb, (255, 255, 255))
        ty = py + pw + int(H * 0.055)

    if text.strip():
        lines = _wrap(text.strip(), f_text, int(W * 0.84), dr)[:2]
        lineh = int(f_text.size * 1.35)
        for i, ln in enumerate(lines):
            try:
                tw = dr.textlength(ln, font=f_text)
            except Exception:
                tw = len(ln) * f_text.size
            dr.text(((W - tw) // 2, ty + i * lineh), ln, font=f_text, fill=th["ink"])
    ImageEnhance.Sharpness(base).enhance(1.05).save(dst, quality=93)
    return dst


# ---------------- 主流程 ----------------
def _parse_map(s):
    m = {}
    for seg in (s or "").split(";"):
        if ":" in seg:
            k, v = seg.split(":", 1)
            if k.strip() and v.strip():
                m[k.strip()] = v.strip()
    return m


def final_path(out, diff):
    return os.path.join(out, "prize.jpg" if not diff else "prize_%s.jpg" % diff)


def staged_name(diff, tag):
    return ("prize_%s_%s.png" % (diff, tag)) if diff else ("prize_%s.png" % tag)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="ai", choices=["ai", "user", "compose"],
                    help="ai=本地引擎生成全身多姿势；user=用户上传；compose=把一张图合成为奖励样式候选")
    ap.add_argument("--init", default="", help="img2img 起始图：默认 assets/normal.png（表情人物）")
    ap.add_argument("--input", default="", help="--mode user/compose 时的素材图")
    ap.add_argument("--out", default="prize", help="输出目录")
    ap.add_argument("--poses", type=int, default=3, help="系统生成几个姿势（1~3）")
    ap.add_argument("--pick", default="", help="从已生成的多张里定案某一张")
    ap.add_argument("--diff", default="", help="这张图的难度归属（normal/hard/hell）；留空=全难度共用")
    ap.add_argument("--per-diff", default="", help="按难度批量出图，逗号分隔，如 normal,hard,hell")
    ap.add_argument("--text", default="", help="图上文字；留空=不带字")
    ap.add_argument("--text-map", default="", help="按难度分别指定文字，格式 normal:字A;hard:字B")
    ap.add_argument("--text-position", default="bottom", choices=["bottom", "top", "none"])
    ap.add_argument("--layouts", default="card,circle,badge", help="compose 候选版式，逗号分隔")
    ap.add_argument("--candidates", type=int, default=3, help="compose 出几个候选供用户挑")
    ap.add_argument("--theme", default="gold", choices=list(THEMES), help="compose 配色主题")
    ap.add_argument("--size", default="900x1200", help="compose 画布，如 900x1200")
    ap.add_argument("--desc", default="the uploaded person, keep facial features and hairstyle",
                    help="人物描述（沿用表情包那套描述，保证同一角色）")
    ap.add_argument("--endpoint", default="", help="sd-server 地址，如 http://127.0.0.1:8790")
    ap.add_argument("--strength", type=float, default=0.80, help="img2img 强度；半身像扩全身建议 0.78~0.88")
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--sampler", default="euler")
    ap.add_argument("--cfg", type=float, default=7.0)
    ap.add_argument("--seed", type=int, default=20261118)
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=1216)
    ap.add_argument("--manifest-only", action="store_true", help="只导出 prompt 清单")
    ap.add_argument("--list", action="store_true", help="只列姿势与 prompt")
    a = ap.parse_args()

    out = os.path.abspath(os.path.expanduser(a.out))
    os.makedirs(out, exist_ok=True)
    tmap = _parse_map(a.text_map)
    diffs = [x.strip() for x in a.per_diff.split(",") if x.strip()] or [a.diff]

    def text_of(d):
        return tmap.get(d, a.text) if d else a.text

    # C. 定案（按难度归属命名：共用=prize.jpg，分难度=prize_<diff>.jpg）
    if a.pick:
        src = os.path.abspath(os.path.expanduser(a.pick))
        if not os.path.exists(src):
            sys.exit("  [错误] 找不到要定案的图: %s" % src)
        dst = final_path(out, a.diff)
        draw_caption(src, dst, text_of(a.diff), a.text_position)
        print("已定案: %s -> %s  (难度: %s)" % (src, dst, a.diff or "全难度共用"))
        return

    # 用户上传
    if a.mode == "user":
        if not a.input:
            sys.exit("  [错误] --mode user 需要 --input 指向用户上传/指定的图片")
        src = os.path.abspath(os.path.expanduser(a.input))
        if not os.path.exists(src):
            sys.exit("  [错误] 用户给的图不存在: %s —— 先确认文件真的在磁盘上" % src)
        for d in diffs:
            dst = final_path(out, d)
            draw_caption(src, dst, text_of(d), a.text_position)
            print("用户惊喜图已入库: %s (%d 字节)  难度=%s"
                  % (dst, os.path.getsize(dst), d or "全难度共用"))
        return

    # compose：本地 Pillow 合成候选（不依赖引擎，最快能出图给用户挑）
    if a.mode == "compose":
        if not a.input:
            sys.exit("  [错误] --mode compose 需要 --input 指向要合成的那张图（用户照片或已定卡通像）")
        src = os.path.abspath(os.path.expanduser(a.input))
        if not os.path.exists(src):
            sys.exit("  [错误] 素材图不存在: %s" % src)
        try:
            W, H = [int(x) for x in a.size.lower().split("x")]
        except Exception:
            W, H = 900, 1200
        lays = [x.strip() for x in a.layouts.split(",") if x.strip()] or list(LAYOUTS)
        lays = lays[:max(1, min(a.candidates, len(lays)))]
        made = []
        for d in diffs:
            for i, lay in enumerate(lays, 1):
                p = os.path.join(out, staged_name(d, "cand%d_%s" % (i, lay)))
                compose(src, p, text_of(d), a.theme, lay, (W, H))
                made.append(p)
                print("  合成 [%-6s] %-6s -> %s" % (d or "共用", lay, p))
        print("\n%d 张候选已出，拼小样给用户挑：" % len(made))
        print("  python {baseDir}/scripts/make_sheet.py --in %s --out %s --cols 3 --title \"惊喜图候选，用哪张？\""
              % (out, os.path.join(out, "sheet_prize.jpg")))
        print("用户选定后：python {baseDir}/scripts/gen_prize.py --pick <选定图> --diff %s --out %s"
              % (a.diff or "normal", out))
        return

    # 系统生成（img2img，按难度批量）
    init = a.init
    if not init:
        for cand in ("assets/normal.png", "normal.png"):
            if os.path.exists(cand):
                init = cand
                break
    if init and not os.path.exists(init):
        sys.exit("  [错误] 起始图不存在: %s" % init)

    poses = POSES[:max(1, min(a.poses, len(POSES)))]
    tasks = []
    for d in diffs:
        for i, (key, cn, pose) in enumerate(poses):
            tasks.append({"diff": d, "key": key, "cn": cn,
                          "seed": a.seed + i * 37 + len(d) * 7,
                          "text": text_of(d),
                          "prompt": "%s, %s, %s" % (a.desc, pose, STYLE),
                          "negative_prompt": PROMPT_NEG,
                          "file": staged_name(d, key)})

    if a.list:
        for t in tasks:
            print("[%s] %-12s %-8s seed=%d\n    %s\n"
                  % (t["diff"] or "共用", t["key"], t["cn"], t["seed"], t["prompt"]))
        return

    man_path = os.path.join(out, "prize_manifest.json")
    manifest = {"mode": "pending", "init": os.path.abspath(init) if init else "",
                "desc": a.desc, "text": a.text, "text_map": tmap,
                "per_diff": a.per_diff, "strength": a.strength, "items": []}

    if a.manifest_only or not a.endpoint:
        for t in tasks:
            manifest["items"].append({**t, "status": "pending",
                                      "hint": "用 locmodel MCP(redraw_image, init_image=%s, strength=%.2f) 或线上出图按此 prompt 生成，另存为 %s"
                                              % (init or "用户照片", a.strength, t["file"])})
        manifest["mode"] = "external"
        json.dump(manifest, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("已导出惊喜图 prompt 清单: %s（%d 张待生成，覆盖难度: %s）"
              % (man_path, len(tasks), "、".join(d or "共用" for d in diffs)))
        print("生成后放到 %s，再跑 make_sheet.py 拼小样给用户挑，最后 --pick 定案。" % out)
        return

    if not probe(a.endpoint):
        sys.exit("引擎不可达: %s。先启动本地 LocModel/sd-server，或改用 --manifest-only 走 MCP/线上路线。"
                 % a.endpoint)

    init_b64 = base64.b64encode(open(init, "rb").read()).decode() if init else ""
    made = []
    for i, t in enumerate(tasks, 1):
        t0 = time.time()
        try:
            b64 = img2img(a.endpoint, init_b64, t["prompt"], t["negative_prompt"], a.strength,
                          a.steps, a.sampler, a.cfg, t["seed"], a.width, a.height)
            p = os.path.join(out, t["file"])
            open(p, "wb").write(base64.b64decode(b64))
            made.append(p)
            t.update(status="done", secs=round(time.time() - t0), path=p)
            print("  [%d/%d] [%-6s] %-12s %s -> %s"
                  % (i, len(tasks), t["diff"] or "共用", t["key"], t["cn"], p))
        except Exception as e:
            t.update(status="failed", error=repr(e))
            print("  [%d/%d] [%-6s] %-12s 失败: %r"
                  % (i, len(tasks), t["diff"] or "共用", t["key"], e))

    manifest["mode"] = "local"
    manifest["items"] = tasks
    json.dump(manifest, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if made:
        print("\n拼小样给用户挑：")
        print("  python {baseDir}/scripts/make_sheet.py --in %s --out %s --cols 3 --title \"惊喜图小样，选哪个？\""
              % (out, os.path.join(out, "sheet_prize.jpg")))
        print("定案（按难度归属）：python {baseDir}/scripts/gen_prize.py --pick <选定图> --diff %s --out %s"
              % (diffs[0] or "normal", out))
    if len(made) == 1 and len(diffs) == 1:
        draw_caption(made[0], final_path(out, diffs[0]), text_of(diffs[0]), a.text_position)
        print("仅 1 张，已直接定案为 %s" % final_path(out, diffs[0]))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
make_sheet.py — 小样确认拼图（v1.1 新增，v1.2 加背景检查）

作用：把一批图拼成一张带编号和中文名的预览图，方便发给用户做"全部通过 / 全部重做 /
      指定重做"或"选哪张当惊喜图"的确认。图片按文件名排序，grid 自动排。

v1.2：默认开启 --check-bg，逐张判定背景是否为利于抠图的纯色（PASS / WARN / FAIL），
      拼图右上角画出该图背景色块，并输出 <out>.bgcheck.json 供 gate.py 对账。
      FAIL 的图必须重生，否则抠图会花边或把主体吃掉。

必须先有这张图，gate.py 的表情门禁才允许写入（--sheet 指向本脚本产物）。
"""
import argparse
import json
import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\Deng.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
CN = {}


def font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def load_cn():
    """从 gen_expressions.py 取中文名映射；取不到就只用文件名。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gen_expressions as ge
        for k, _e, cn in ge.EXPRESSIONS:
            CN[k] = cn
    except Exception:
        pass


# v1.2：小样背景必须是「利于抠图」的纯色。预设色值与 gen_expressions.BG_PRESETS 对齐。
BG_OK = {"#FF00FF": "magenta", "#00FF00": "green", "#0000FF": "blue", "#FFFFFF": "white"}
BG_TOL = 30


def bg_check(path, tol=BG_TOL):
    """检查单张图的背景是否合格（四角是否一致、是否预设纯色、背景占比够不够）。
    返回 dict: {hex, name, ok, cover, corner, verdict, note}"""
    r = {"hex": "", "name": "", "ok": False, "cover": 0.0, "corner": 0.0,
         "verdict": "FAIL", "note": ""}
    try:
        im = Image.open(path)
    except Exception as e:
        r["note"] = "无法打开(%r)" % (e,)
        return r
    if im.mode == "RGBA" and im.split()[-1].getextrema()[0] < 250:
        r.update(hex="", name="透明", ok=True, cover=1.0, corner=1.0, verdict="PASS",
                 note="已带 alpha，无需抠图")
        return r
    rgb = im.convert("RGB")
    w, h = rgb.size
    k = max(4, min(20, int(min(w, h) * 0.04)))
    mids = [(0, 0, k, k), (w - k, 0, w, k), (0, h - k, k, h), (w - k, h - k, w, h),
            (max(0, w // 2 - k // 2), 0, min(w, w // 2 + k // 2), k),
            (max(0, w // 2 - k // 2), h - k, min(w, w // 2 + k // 2), h)]
    px = []
    for b in mids:
        px += list(rgb.crop(b).getdata())
    med = tuple(sorted(p[i] for p in px)[len(px) // 2] for i in range(3))
    corner = sum(1 for p in px if max(abs(p[i] - med[i]) for i in range(3)) <= tol) / float(len(px))
    small = list(rgb.resize((64, 64)).getdata())
    cover = sum(1 for p in small if max(abs(p[i] - med[i]) for i in range(3)) <= tol) / float(len(small))
    hexv = "#%02X%02X%02X" % med
    r.update(hex=hexv, corner=round(corner, 2), cover=round(cover, 2))
    if corner < 0.6:
        r.update(verdict="FAIL", note="四角颜色不一致（渐变/场景背景），抠图必花边，必须重出")
    elif cover < 0.15:
        r.update(verdict="FAIL", note="背景占比 %.0f%% 过小（人物铺满画面），抠图无背景可依" % (cover * 100))
    elif hexv in BG_OK:
        r.update(name=BG_OK[hexv], ok=True, verdict="PASS", note="纯色 %s，占比 %.0f%%" % (BG_OK[hexv], cover * 100))
    else:
        r.update(verdict="WARN", note="纯色但非预设色 %s，可抠但建议换成 magenta/green" % hexv)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True, help="图片目录")
    ap.add_argument("--out", default="sheet.jpg", help="输出拼图路径")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--cell", type=int, default=260, help="单格边长（含留白）")
    ap.add_argument("--title", default="", help="大标题，如 表情小样 11 张")
    ap.add_argument("--check-bg", dest="check_bg", action="store_true", default=True,
                    help="v1.2 默认开启：检查每张小样背景是否为利于抠图的纯色，并写 bgcheck.json")
    ap.add_argument("--no-check-bg", dest="check_bg", action="store_false", help="关闭背景检查")
    ap.add_argument("--bg-json", default="", help="背景检查报告输出路径，默认 <out>.bgcheck.json")
    a = ap.parse_args()

    indir = os.path.abspath(os.path.expanduser(a.indir))
    if not os.path.isdir(indir):
        sys.exit("  [错误] 目录不存在: %s" % indir)

    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = sorted(n for n in os.listdir(indir) if n.lower().endswith(exts))
    if not files:
        sys.exit("  [错误] %s 下没有图片" % indir)

    load_cn()
    cols = max(1, min(a.cols, len(files)))
    rows = (len(files) + cols - 1) // cols
    cell = a.cell
    pad = 10
    label_h = 34
    title_h = 46 if a.title else 0
    W = cols * (cell + pad) + pad
    H = rows * (cell + label_h + pad) + pad + title_h
    sheet = Image.new("RGB", (W, H), (250, 250, 252))
    dr = ImageDraw.Draw(sheet)

    if a.title:
        dr.text((pad + 4, 12), a.title, font=font(26), fill=(24, 24, 28))

    f_lab = font(17)
    reports = []
    for i, n in enumerate(files):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = title_h + pad + r * (cell + label_h + pad)
        src = os.path.join(indir, n)
        try:
            im = Image.open(src)
        except Exception as e:
            print("  [警告] 跳过无法打开的文件 %s (%r)" % (n, e))
            continue
        # v1.2：背景检查 —— 小样背景必须是利于抠图的纯色，不合格当场提示重出
        chk = None
        if a.check_bg:
            chk = bg_check(src)
            chk["file"] = n
            reports.append(chk)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        if im.mode == "RGBA":
            bg.alpha_composite(im)
            im = bg
        im.thumbnail((cell, cell), Image.LANCZOS)
        ox = x + (cell - im.width) // 2
        oy = y + (cell - im.height) // 2
        box = Image.new("RGB", (cell, cell), (255, 255, 255))
        box.paste(im.convert("RGB"), (ox - x, oy - y))
        sheet.paste(box, (x, y))
        dr.rectangle([x, y, x + cell - 1, y + cell - 1], outline=(214, 216, 222))
        if chk is not None and chk["hex"]:
            try:
                hx = chk["hex"].lstrip("#")
                rc = tuple(int(hx[j:j + 2], 16) for j in (0, 2, 4))
            except Exception:
                rc = (200, 200, 200)
            dr.rectangle([x + cell - 26, y + 6, x + cell - 6, y + 26], fill=rc, outline=(90, 90, 90))

        key = os.path.splitext(n)[0]
        cn = CN.get(key, "")
        tip = "%d. %s" % (i + 1, ("%s %s" % (key, cn)).strip())
        try:
            tw = dr.textlength(tip, font=f_lab)
        except Exception:
            tw = len(tip) * 9
        while tw > cell - 8 and len(tip) > 6:
            tip = tip[:-2] + "…"
            tw = len(tip) * 9
        dr.text((x + max(2, (cell - tw) // 2), y + cell + 8), tip, font=f_lab, fill=(58, 60, 70))

    outp = os.path.abspath(os.path.expanduser(a.out))
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    if outp.lower().endswith((".jpg", ".jpeg")):
        sheet.save(outp, quality=88)
    else:
        sheet.save(outp)
    print("拼图已生成: %s  (%d 张 / %dx%d / %.1f KB)" % (
        outp, len(files), sheet.width, sheet.height, os.path.getsize(outp) / 1024.0))

    # v1.2：背景检查报告（gate.py / build_game.py 构建前会对账，FAIL 必须重出）
    if reports:
        npass = sum(1 for x in reports if x["verdict"] == "PASS")
        nwarn = sum(1 for x in reports if x["verdict"] == "WARN")
        nfail = [x for x in reports if x["verdict"] == "FAIL"]
        print("\n背景检查（小样背景必须是利于抠图的纯色）:")
        for x in reports:
            print("  [%-4s] %-24s %-8s %s" % (x["verdict"], x["file"], x["hex"] or "-", x["note"]))
        print("  汇总: %d PASS / %d WARN / %d FAIL" % (npass, nwarn, len(nfail)))
        jp = a.bg_json or (os.path.splitext(outp)[0] + ".bgcheck.json")
        jp = os.path.abspath(os.path.expanduser(jp))
        os.makedirs(os.path.dirname(jp) or ".", exist_ok=True)
        with open(jp, "w", encoding="utf-8") as f:
            json.dump({"sheet": outp, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "pass": npass, "warn": nwarn,
                       "fail": [x["file"] for x in nfail], "items": reports},
                      f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        print("  报告: %s" % jp)
        if nfail:
            print("\n  [必须处理] 这些图背景不合格，抠图会花边或残缺，需按下列命令重生：")
            for x in nfail:
                print("    --only %s   (%s)" % (os.path.splitext(x["file"])[0], x["note"]))
            print("    重生时加 --bg magenta（或 green/blue/white），prompt 里不得出现场景/渐变")

    print("\n请把这张图发给用户确认；用户回复后再写 gate.py --expressions 或 --prize --pick")


if __name__ == "__main__":
    main()

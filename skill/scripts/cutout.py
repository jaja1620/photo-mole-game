# -*- coding: utf-8 -*-
"""cutout.py — 表情图抠图 + 统一画布归一化（纯 cv2/numpy，无需 rembg）

用途:
  1) 把 AI 生成的表情图（通常带纯色/渐变背景）抠成透明 PNG
  2) 把一组表情统一到相同画布与人物基准高度，保证游戏里换表情时人物不跳动

用法:
  python cutout.py --in raw/ --out assets/                 # 批量抠图
  python cutout.py --in raw/ --out assets/ --normalize     # 抠图 + 统一画布
  python cutout.py --in one.png --out one_cut.png          # 单张
  python cutout.py --in raw/ --out assets/ --normalize --chroma auto   # v1.2 推荐写法

抠图策略（v1.2 起五步递减）:
  - 已有有效 alpha 直接复用，不重复抠
  - 路线 0 色度键（v1.2 主路线）：小样背景按 v1.2 规定就是纯色（magenta/green/blue/white），
    色值优先取 --bg-hex，其次 raw/manifest.json 里的 bg.hex，再次四角采样。
    与目标色色差 < tol 且与外框连通的区域判为背景，纯色下比 GrabCut 干净、不留白边。
  - 路线 1 GrabCut + 引导 mask：背景非纯色（四角一致度 < 0.55）时的主力，
    四角/四边=确定背景，中央带=可能前景，正中心=确定前景
  - 路线 2 四边 floodFill 兜底：GrabCut 前景占比异常时启用
  - 统一清理：最大连通域 + close 补断口 + 填内部洞 + 去小碎块
  - 边缘 1px 羽化，避免锯齿
"""
import argparse, json, os, sys
import numpy as np
import cv2

def has_alpha(img):
    return img.shape[2] == 4 and int(img[:, :, 3].min()) < 250 and int((img[:, :, 3] < 16).mean() * 100) > 5

def _refine_mask(fg, close_k=9):
    """清理 mask：只留最大主体连通域、闭运算补断口、填内部洞、去小碎块。"""
    h, w = fg.shape
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
    if n > 1:
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (lab == idx).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((close_k, close_k), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # 填内部空洞（保留外部透明）
    ff = fg.copy()
    mm = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, mm, (0, 0), 1)
    fg = fg | (1 - ff).astype(np.uint8)
    return fg

def _grabcut_cut(rgb):
    """GrabCut + 引导 mask：四角/四边确定背景、中央确定前景，抗'描边浅色背景'翻车。
    返回 (fg_mask, ok)；背景与主体颜色接近时 floodFill 会把白衣服当背景删掉，
    GrabCut 用颜色模型 + 边缘 + 空间连续性，能靠粗黑描边把人物分离出来。"""
    h, w = rgb.shape[:2]
    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    cx0, cy0, cx1, cy1 = int(w*0.2), int(h*0.12), int(w*0.8), int(h*0.9)
    gc[cy0:cy1, cx0:cx1] = cv2.GC_PR_FGD
    sx0, sy0, sx1, sy1 = int(w*0.35), int(h*0.25), int(w*0.65), int(h*0.7)
    gc[sy0:sy1, sx0:sx1] = cv2.GC_FGD
    bd = int(min(h, w) * 0.035)
    gc[:bd, :] = gc[-bd:, :] = cv2.GC_BGD
    gc[:, :bd] = gc[:, -bd:] = cv2.GC_BGD
    qx, qy = int(w*0.12), int(h*0.10)
    gc[:qy, :qx] = gc[:qy, -qx:] = cv2.GC_BGD
    gc[-qy:, :qx] = gc[-qy:, -qx:] = cv2.GC_BGD
    bgd = np.zeros((1, 65), np.float64); fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(rgb, gc, None, bgd, fgd, 10, cv2.GC_INIT_WITH_MASK)
    fg = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    return fg

def _parse_hex(h):
    h = str(h).strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


def sample_bg_hex(rgb):
    """从四角与上下边中点采样背景主色 → (#RRGGBB, 一致度0~1)。
    一致度低说明是渐变/场景背景，色度键不适用，应回退 GrabCut。"""
    h, w = rgb.shape[:2]
    k = max(4, min(24, int(min(h, w) * 0.03)))
    patches = [rgb[:k, :k], rgb[:k, -k:], rgb[-k:, :k], rgb[-k:, -k:],
               rgb[:k, max(0, w // 2 - k // 2): w // 2 + k // 2],
               rgb[-k:, max(0, w // 2 - k // 2): w // 2 + k // 2]]
    px = np.concatenate([p.reshape(-1, 3) for p in patches]).astype(np.int32)
    med = np.median(px, axis=0).astype(np.int32)
    near = (np.abs(px - med).max(axis=1) <= 26).mean()
    return "#%02X%02X%02X" % tuple(int(v) for v in med), float(near)


def _chroma_cut(rgb, hex_color, tol=34):
    """色度键抠图（v1.2）：背景 = 与目标色色差 < tol 且与画面外框连通的区域。
    先把图贴到同色画布上再做 floodFill，可保证贴边的人物不被误判为背景；
    纯色背景（magenta/green/blue/white）下比 GrabCut 干净、且不留半透明白边。"""
    target = _parse_hex(hex_color)
    if target is None:
        return None
    h, w = rgb.shape[:2]
    pad = 40
    canvas = np.full((h + 2 * pad, w + 2 * pad, 3), target, np.uint8)
    canvas[pad:pad + h, pad:pad + w] = rgb
    mask = np.zeros((canvas.shape[0] + 2, canvas.shape[1] + 2), np.uint8)
    cv2.floodFill(canvas, mask, (0, 0), (255, 255, 255), (tol,) * 3, (tol,) * 3,
                  4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE)
    bg = (mask[1:-1, 1:-1] > 0).astype(np.uint8)[pad:pad + h, pad:pad + w]
    diff = np.abs(rgb.astype(np.int32) - np.array(target, np.int32)).max(axis=2)
    bg = cv2.bitwise_or(bg, (diff <= tol).astype(np.uint8))
    return (1 - bg).astype(np.uint8)


def cut_one(path, tol=18, close_k=9, feather=1, chroma="auto", bg_hex=""):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None: raise SystemExit("读取失败: " + path)
    if has_alpha(img):
        return img, "alpha-reuse"
    rgb = img[:, :, :3]
    h, w = rgb.shape[:2]

    # 路线 0（v1.2 主路线）：纯色背景 → 色度键。背景色取 --bg-hex/--chroma 指定值，
    # 未指定则四角采样自动识别；采样一致性低于阈值说明不是纯色背景，直接跳过。
    fg, how = None, ""
    if chroma != "off":
        target = bg_hex or (chroma if chroma not in ("auto", "") else "")
        if not target:
            target, consistent = sample_bg_hex(rgb)
            if consistent < 0.55:
                print("      [提示] 四角背景一致度 %.2f 偏低（疑似渐变/场景），跳色度键走 GrabCut" % consistent)
                target = ""
        if target:
            m = _chroma_cut(rgb, target, tol=max(tol, 34))
            if m is not None:
                m = _refine_mask(m, close_k)
                if 0.05 <= m.mean() <= 0.95:
                    fg, how = m, "chroma %s" % target

    # 路线 1：GrabCut 引导 mask（对浅色背景 + 白衣服的卡通立绘最稳）
    if fg is None:
        fg = _refine_mask(_grabcut_cut(rgb), close_k)
        how = "grabcut"

    # 兜底：若 GrabCut 前景占比异常，退回四边 floodFill
    if fg.mean() < 0.04 or fg.mean() > 0.97:
        mask = np.zeros((h + 2, w + 2), np.uint8)
        seeds = []
        for x in range(0, w, max(1, w // 12)): seeds += [(x, 0), (x, h - 1)]
        for y in range(0, h, max(1, h // 12)): seeds += [(0, y), (w - 1, y)]
        bg = np.zeros((h, w), np.uint8)
        flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE
        for (x, y) in seeds:
            if bg[y, x]: continue
            m2 = mask.copy()
            cv2.floodFill(rgb.copy(), m2, (x, y), 255, (tol,) * 3, (tol,) * 3, flags)
            bg |= (m2[1:-1, 1:-1] > 0).astype(np.uint8)
        fg = _refine_mask((1 - bg).astype(np.uint8), close_k)
        how = "floodfill-fallback"
    if fg.mean() < 0.02 or fg.mean() > 0.98:
        raise SystemExit("抠图失败（前景占比 %.3f）: %s" % (fg.mean(), path))

    alpha = (fg * 255).astype(np.uint8)
    if feather > 0:
        alpha = cv2.GaussianBlur(alpha, (feather * 2 + 1, feather * 2 + 1), 0)
        alpha = np.where(fg > 0, np.maximum(alpha, 180), alpha).astype(np.uint8)
    out = np.dstack([rgb, alpha])
    return out, how

def bbox_of(alpha):
    ys, xs = np.where(alpha > 8)
    if len(ys) == 0: return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

def normalize(imgs, canvas=(640, 800), pad_top=0.06, pad_bottom=0.03):
    """统一画布：所有人物的"头顶"与"脚底"对齐到同一基准，水平居中"""
    CW, CH = canvas
    boxes = [bbox_of(im[:, :, 3]) for im in imgs]
    heights = [b[3] - b[1] for b in boxes if b]
    if not heights: return imgs
    target_h = int(CH * (1 - pad_top - pad_bottom))
    outs = []
    for im, b in zip(imgs, boxes):
        if not b: outs.append(np.zeros((CH, CW, 4), np.uint8)); continue
        x0, y0, x1, y1 = b
        sub = im[y0:y1, x0:x1]
        # 逐图缩放到同一人物高度：保证头顶/脚底对齐，且不会超出画布（旧版按 median 缩放会越界）
        scale = target_h / float(sub.shape[0])
        nh, nw = max(1, int(sub.shape[0] * scale)), max(1, int(sub.shape[1] * scale))
        if nw > CW * 0.98:                     # 太宽则按宽度回缩
            r = (CW * 0.98) / nw
            nh, nw = int(nh * r), int(nw * r)
        sub = cv2.resize(sub, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        cvs = np.zeros((CH, CW, 4), np.uint8)
        oy = int(CH * pad_top)
        ox = (CW - nw) // 2
        cvs[oy:oy + nh, ox:ox + nw] = sub
        outs.append(cvs)
    return outs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--tol", type=int, default=18)
    ap.add_argument("--close", type=int, default=9)
    ap.add_argument("--feather", type=int, default=1)
    ap.add_argument("--normalize", action="store_true", help="统一画布（推荐开启，避免游戏内换表情跳动）")
    ap.add_argument("--canvas", default="640x800")
    ap.add_argument("--chroma", default="auto",
                    help="色度键背景色：auto=读 manifest.json 的 bg.hex、缺失则四角采样；也可直接给 #RRGGBB；off=只用 GrabCut")
    ap.add_argument("--bg-hex", default="", help="直接指定背景色 #RRGGBB（优先于 --chroma）")
    a = ap.parse_args()

    CW, CH = [int(x) for x in a.canvas.lower().split("x")]
    single = os.path.isfile(a.src)
    files = [a.src] if single else [os.path.join(a.src, f) for f in sorted(os.listdir(a.src))
                                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    if not files: raise SystemExit("没有输入图片")
    if not single: os.makedirs(a.dst, exist_ok=True)

    # v1.2：背景色优先取 --bg-hex，其次 gen_expressions.py 写下的 manifest.json 里的 bg.hex
    bg_hex = a.bg_hex.strip()
    if not bg_hex and a.chroma in ("auto", ""):
        mp = os.path.join(os.path.dirname(os.path.abspath(files[0])), "manifest.json")
        if os.path.exists(mp):
            try:
                bg_hex = ((json.load(open(mp, encoding="utf-8")) or {}).get("bg") or {}).get("hex", "")
            except Exception:
                bg_hex = ""
        if bg_hex:
            print("  背景色取自 manifest: %s（色度键模式）" % bg_hex)
        else:
            print("  未找到 manifest 中的背景色，改为四角采样自动识别")

    imgs, hows, names = [], [], []
    for p in files:
        try:
            im, how = cut_one(p, a.tol, a.close, a.feather, a.chroma, bg_hex)
            imgs.append(im); hows.append(how); names.append(os.path.basename(p))
            print("  %-24s %-12s %dx%d" % (os.path.basename(p), how, im.shape[1], im.shape[0]))
        except SystemExit as e:
            print("  [SKIP] %s" % e)

    if a.normalize and len(imgs) > 1:
        imgs = normalize(imgs, (CW, CH))
        print("  已统一画布 %dx%d" % (CW, CH))

    for im, nm in zip(imgs, names):
        base = os.path.splitext(nm)[0] + ".png"
        out = a.dst if single else os.path.join(a.dst, base)
        cv2.imwrite(out, im)
        print("  -> %s (%d 字节)" % (out, os.path.getsize(out)))

if __name__ == "__main__":
    main()

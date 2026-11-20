# -*- coding: utf-8 -*-
"""cutout.py — 表情图抠图 + 统一画布归一化（v1.3.0：抠前分析 / 主体保护 / 抠后校验 / 对照图）

用途:
  1) 把 AI 生成的表情图（通常带纯色/渐变背景）抠成透明 PNG
  2) 把一组表情统一到相同画布与人物基准高度，保证游戏里换表情时人物不跳动
  3) v1.3.0 起共四件事，抠图只是一个环节：**抠前分析 → 定参 → 抠图 → 抠后比对**

用法:
  # ① 抠前分析（不出图）：看背景一致度、背景色、主体占比、推荐参数与风险
  python cutout.py --in raw/ --analyze
  python cutout.py --in raw/ --analyze --out assets/        # 顺带把分析结果写到 assets/cutout.analyze.json

  # ② 按分析结果定参抠图（--tol/--bg-hex 用分析里给的值，别盲调）
  python cutout.py --in raw/ --out assets/ --normalize --chroma auto --tol 32

  # ③ 抠后比对（必做）：逐张指标 + PASS/WARN/FAIL 报告
  python cutout.py --in raw/ --out assets/ --normalize --chroma auto --verify --compare

  # ④ 只看比对图（已有 assets/ 时）
  python cutout.py --in raw/ --out assets/ --compare --compare-only
  python cutout.py --in one.png --out one_cut.png

抠图策略（v1.2 起五步递减，v1.3 加主体保护）:
  - 已有有效 alpha 直接复用，不重复抠
  - 路线 0 色度键（主路线）：背景按纯色处理，色值优先取 --bg-hex，其次 raw/manifest.json 的
    bg.hex，再次四角采样。与目标色色差 < tol 且与外框连通的区域判为背景。
  - 路线 1 GrabCut 引导 mask：背景非纯色（四角一致度 < 0.55）时的主力。
  - 路线 2 四边 floodFill 兜底。
  - 统一清理：最大连通域 + close 补断口 + 填内部洞 + 去小碎块 + 边缘 1px 羽化。
  - **v1.3 主体保护（默认开启）**：色度键结果必须与 GrabCut 前景交叉校验，落在“主体内部核心区
    但被色度键判成背景”的像素会被回填。也就是说 **人物主体、衣服、配件、头发、眼镜、饰品不会
    因为颜色接近背景而被整块扣掉**。副作用是极端情况下可能回填少量背景，所以抠后必须看
    --verify 报告与 --compare 对照图。真的不行就换背景色重生，不要在这里硬调参数。

抠后校验指标（--verify，写 cutout.report.json）:
  **v1.3.0 修订：判定不得用自身 mask 自证。** 旧版拿"自身 GrabCut 掩膜腐蚀后的内部"当主体基准，
  等于自己判自己——掩膜把头发/衣领一起扣掉时基准跟着一起少，保留率恒为 100%，于是 05_angry
  "两侧头发被削 + 肩部衣领被抠掉"也被判成 PASS。
  现在每次校验都**单独**估一份"独立主体基准"（baseline_subject：与本次抠图无关、不受 --chroma
  影响的两套 GrabCut + 四边泛洪反推的背景之外区域），并集得到主体上界 IB（宁可多保），IB 再腐蚀
  2% 短边得到主体核心 IB_core。所有指标一律以 IB / IB_core 为参照：
  - keep_ratio        主体保留率：IB_core 保住了多少，<0.90 FAIL，<0.95 WARN
  - iou               与 IB 的 IoU：轮廓是否对得上主体，<0.75 FAIL
  - hole_rate         内部孔洞率：与外界不连通的被掏空面积占比，1.5%~4% WARN，>4% FAIL
  - edge_cut_ratio    贴边裁切：主体边界像素落在画幅四边（1.2% 短边内）的占比，>3% FAIL，>0.8% WARN
  - comp2_ratio       连通域断裂：第二大连通域/最大连通域，>0.25 FAIL，>0.05 WARN
  - dent_ratio        轮廓削切嫌疑：左右边界相对"正常轮廓包络"的最大内向凹陷 ÷ 主体高度，
                      >0.65 FAIL，>0.48 WARN（头发两侧/肩部衣领被整块削掉就是这种形态）
  - fg_ratio          前景占比：0.08~0.85 PASS（过低=人被吃掉，过高=背景没抠掉）
  - edge_color_diff   边缘色差：前景边缘像素与背景色的平均距离，≥50 PASS，<40 FAIL
  只要没有 FAIL，WARN 也必须逐条看对照图确认；FAIL 时进程以退出码 2 结束，并打印返工 key
  （可直接喂给 gen_expressions.py --only）。
"""
import argparse
import json
import os
import sys

import numpy as np
import cv2

VERSION = "1.3.0"

# 利于抠图的纯色预设（与 gen_expressions.py 的 BG_PRESETS 保持一致）
BG_PRESETS = {
    "magenta": "#FF00FF",
    "green": "#00FF00",
    "blue": "#0000FF",
    "white": "#FFFFFF",
}

# 抠后校验阈值（v1.3.0：全部以"独立主体基准"为参照，禁止用自身 mask 自证）
T_KEEP_PASS, T_KEEP_WARN = 0.95, 0.90        # 主体保留率 keep_ratio
T_IOU_FAIL = 0.75                            # 与独立基准 mask 的 IoU
T_HOLE_PASS, T_HOLE_WARN = 0.015, 0.040      # 内部被挖孔洞占比
T_EDGE_CUT_WARN, T_EDGE_CUT_FAIL = 0.008, 0.030   # 主体边界贴在画幅四边的像素占比
T_COMP2_WARN, T_COMP2_FAIL = 0.05, 0.25      # 第二大连通域占比（主体断裂）
T_DENT_WARN, T_DENT_FAIL = 0.48, 0.65        # 轮廓凹陷深度 / 主体高度（削切嫌疑）
T_DENT_HARD, T_DENT_AREA = 0.50, 0.01        # 凹陷 >50% 主体高度且缺口面积 >1% 主体 → 直接 FAIL（WARN 不拦构建，坏图会进游戏）
FG_RATIO_PASS = (0.08, 0.85)
FG_RATIO_WARN = (0.05, 0.95)
T_EDGE_PASS, T_EDGE_WARN = 50.0, 40.0        # 边缘色差（旧值 60 会把边缘干净的图误判 WARN，已重标定）

STATUS_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def has_alpha(img):
    return (img.ndim == 3 and img.shape[2] == 4
            and int(img[:, :, 3].min()) < 250
            and int((img[:, :, 3] < 16).mean() * 100) > 5)


def _parse_hex(h):
    h = str(h).strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


def _hex_of(rgb_triple):
    return "#%02X%02X%02X" % tuple(int(max(0, min(255, v))) for v in rgb_triple)


def _color_dist(rgb, hex_color):
    """逐像素与目标色的最大通道差（BGR 输入）。"""
    t = _parse_hex(hex_color)
    if t is None:
        return None
    tb, tg, tr = t[2], t[1], t[0]  # rgb -> bgr 顺序对齐
    diff = np.abs(rgb.astype(np.int32) - np.array([tb, tg, tr], np.int32)).max(axis=2)
    return diff


def _euclid(rgb, bgr_triple):
    d = rgb.astype(np.float64) - np.array(bgr_triple, np.float64)
    return np.sqrt((d ** 2).sum(axis=2))


def _kernel(px):
    px = max(0, int(px))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px * 2 + 1, px * 2 + 1))


def _erode(mask, px):
    px = int(px)
    return mask if px <= 0 else cv2.erode(mask, _kernel(px))


def _dilate(mask, px):
    px = int(px)
    return mask if px <= 0 else cv2.dilate(mask, _kernel(px))


def _fill_holes(mask):
    """填内部空洞，保留与画面外框连通的透明区。"""
    mask = (mask > 0).astype(np.uint8)
    h, w = mask.shape
    ff = mask.copy()
    mm = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, mm, (0, 0), 1)
    return mask | (1 - ff).astype(np.uint8)


def _refine_mask(fg, close_k=9):
    """清理 mask：只留最大主体连通域、闭运算补断口、填内部洞、去小碎块。"""
    fg = (fg > 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
    if n > 1:
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (lab == idx).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((max(1, int(close_k)),) * 2, np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return _fill_holes(fg)


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
    # BGR 中值 → #RRGGBB
    return _hex_of([med[2], med[1], med[0]]), float(near)


def _grabcut_cut(rgb, max_side=900):
    """GrabCut + 引导 mask：四角/四边确定背景、中央确定前景，抗'描边浅色背景'翻车。
    返回 (fg_mask, ok)；背景与主体颜色接近时 floodFill 会把白衣服当背景删掉，
    GrabCut 用颜色模型 + 边缘 + 空间连续性，能靠粗黑描边把人物分离出来。"""
    h, w = rgb.shape[:2]
    scale = 1.0
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
    work = cv2.resize(rgb, (max(2, int(w * scale)), max(2, int(h * scale))),
                      interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    hh, ww = work.shape[:2]
    gc = np.full((hh, ww), cv2.GC_PR_BGD, np.uint8)
    cx0, cy0, cx1, cy1 = int(ww * 0.2), int(hh * 0.12), int(ww * 0.8), int(hh * 0.9)
    gc[cy0:cy1, cx0:cx1] = cv2.GC_PR_FGD
    sx0, sy0, sx1, sy1 = int(ww * 0.35), int(hh * 0.25), int(ww * 0.65), int(hh * 0.7)
    gc[sy0:sy1, sx0:sx1] = cv2.GC_FGD
    bd = max(1, int(min(hh, ww) * 0.035))
    gc[:bd, :] = gc[-bd:, :] = cv2.GC_BGD
    gc[:, :bd] = gc[:, -bd:] = cv2.GC_BGD
    qx, qy = max(1, int(ww * 0.12)), max(1, int(hh * 0.10))
    gc[:qy, :qx] = gc[:qy, -qx:] = cv2.GC_BGD
    gc[-qy:, :qx] = gc[-qy:, -qx:] = cv2.GC_BGD
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(work, gc, None, bgd, fgd, 10, cv2.GC_INIT_WITH_MASK)
    fg = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    if scale < 1:
        fg = cv2.resize(fg, (w, h), interpolation=cv2.INTER_NEAREST)
    return fg


def _chroma_cut(rgb, hex_color, tol=34):
    """色度键抠图：背景 = 与目标色色差 < tol 且与画面外框连通的区域。
    先把图贴到同色画布上再做 floodFill，可保证贴边的人物不被误判为背景。"""
    target = _parse_hex(hex_color)
    if target is None:
        return None
    h, w = rgb.shape[:2]
    pad = 40
    tb, tg, tr = target[2], target[1], target[0]
    canvas = np.full((h + 2 * pad, w + 2 * pad, 3), (tb, tg, tr), np.uint8)
    canvas[pad:pad + h, pad:pad + w] = rgb
    mask = np.zeros((canvas.shape[0] + 2, canvas.shape[1] + 2), np.uint8)
    cv2.floodFill(canvas, mask, (0, 0), (255, 255, 255), (tol,) * 3, (tol,) * 3,
                  4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE)
    bg = (mask[1:-1, 1:-1] > 0).astype(np.uint8)[pad:pad + h, pad:pad + w]
    diff = _color_dist(rgb, hex_color)
    bg = cv2.bitwise_or(bg, (diff <= tol).astype(np.uint8))
    return (1 - bg).astype(np.uint8)


# --------------------------------------------------------------------------- #
# v1.3 主体保护：色度键结果与 GrabCut 前景交叉校验，禁止把主体/衣服/配件扣掉
# --------------------------------------------------------------------------- #
def protect_subject(fg_chroma, ref_fg, radius=None, max_leak_ratio=0.30):
    """把「主体核心区但被色度键判成背景」的像素回填。

    参数:
      fg_chroma  色度键前景 mask
      ref_fg     参照前景（GrabCut 清理后的 mask），代表“主体大概长在哪”
      radius     腐蚀半径（像素）；None/0 时按图像短边 2.5% 自动取值
      max_leak_ratio 单个回填连通域允许的最大面积占比，超过且没有被前景包住，
                     判为“背景泄漏”（背景色与主体同色时 GrabCut 可能多吃背景）
    返回:
      (protected_mask, info{kept_px, kept_ratio, dropped_leak_px, components})
    """
    fg_chroma = (fg_chroma > 0).astype(np.uint8)
    ref_fg = (ref_fg > 0).astype(np.uint8)
    h, w = fg_chroma.shape
    if radius is None or int(radius) <= 0:
        radius = max(3, int(min(h, w) * 0.025))
    radius = int(radius)

    core = _erode(ref_fg, radius)                       # 参照主体的内部（可信核心）
    guard = np.zeros((h, w), np.uint8)                  # 贴边一圈不保护：真背景通常在边上
    g = max(1, int(min(h, w) * 0.02))
    guard[:g, :] = guard[-g:, :] = 1
    guard[:, :g] = guard[:, -g:] = 1

    cand = ((core > 0) & (fg_chroma == 0) & (guard == 0)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, 8)
    keep = np.zeros((h, w), np.uint8)
    leak_px = 0
    comps = 0
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area <= 0:
            continue
        comp = (lab == i).astype(np.uint8)
        ring = (_dilate(comp, 3) > 0) & (comp == 0)
        ring_n = int(ring.sum())
        surrounded = (float(((ring) & (fg_chroma > 0)).sum()) / ring_n) if ring_n else 0.0
        big_leak = area > max_leak_ratio * h * w and surrounded < 0.5
        if big_leak:
            leak_px += area
            continue
        keep |= comp
        comps += 1

    out = fg_chroma | keep
    out = _fill_holes(out)                              # 回填后再补一遍内部孔洞
    info = {
        "radius": radius,
        "kept_px": int(keep.sum()),
        "kept_ratio": round(float(keep.sum()) / float(max(1, core.sum())), 4),
        "dropped_leak_px": int(leak_px),
        "components": comps,
        "protected": int(keep.sum()) > 0,
    }
    return out.astype(np.uint8), info


# --------------------------------------------------------------------------- #
# 抠前分析
# --------------------------------------------------------------------------- #
def suggest_bg(rgb, ref_fg, current_hex=""):
    """在四种预设纯色里挑一个离主体颜色最远的，供“换背景色重生”参考。"""
    px = rgb[ref_fg > 0]
    if px.size == 0:
        return None
    if len(px) > 20000:
        px = px[::max(1, len(px) // 20000)]
    px = px.astype(np.int32)
    best = None
    for nm, hx in BG_PRESETS.items():
        t = _parse_hex(hx)
        tb, tg, tr = t[2], t[1], t[0]
        d = np.sqrt(((px - np.array([tb, tg, tr], np.int32)) ** 2).sum(axis=1)).astype(np.float64)
        p10 = float(np.percentile(d, 10))
        if best is None or p10 > best["min_dist_p10"]:
            best = {"name": nm, "hex": hx, "min_dist_p10": round(p10, 1)}
    if best and current_hex:
        cur = _parse_hex(current_hex)
        if cur:
            cb, cg, cr = cur[2], cur[1], cur[0]
            cd = np.sqrt(((px - np.array([cb, cg, cr], np.int32)) ** 2).sum(axis=1)).astype(np.float64)
            best["current_p10"] = round(float(np.percentile(cd, 10)), 1)
            best["worth_switch"] = bool(best["min_dist_p10"] > best["current_p10"] * 1.5 + 20)
    return best


def analyze_image(path, img, bg_hex_pref="", tol=18):
    """抠前分析（不出图）：背景一致度、背景色、主体占比、推荐参数、风险提示。"""
    h, w = img.shape[:2]
    rep = {"file": os.path.basename(path), "path": os.path.abspath(path),
           "size": "%dx%d" % (w, h), "has_alpha": bool(img.ndim == 3 and img.shape[2] == 4
                                                      and has_alpha(img))}
    rgb = img[:, :, :3]

    if rep["has_alpha"]:
        fg = (img[:, :, 3] > 127).astype(np.uint8)
        ref = _refine_mask(fg, 9)
        rep.update({"mode": "alpha-reuse", "bg_hex": "", "bg_consistency": 1.0,
                    "bg_source": "图片自带 alpha", "subject_ratio": round(float(ref.mean()), 3),
                    "bg_ratio": round(1 - float(ref.mean()), 3), "near_bg_ratio": 0.0,
                    "recommend": {"mode": "alpha-reuse", "tol": 0, "bg_hex": "", "chroma": "auto"},
                    "risks": ["图片本身带透明通道，将直接复用 alpha，不做抠图"]})
        return rep

    if bg_hex_pref:
        bg_hex, cons, src = bg_hex_pref, 1.0, "manifest/参数指定"
    else:
        bg_hex, cons = sample_bg_hex(rgb)
        src = "四角+上下边中点采样"

    ref = _refine_mask(_grabcut_cut(rgb), 9)
    subj = float(ref.mean())
    core = _erode(ref, max(3, int(min(h, w) * 0.02)))
    core_n = int(core.sum())
    diff = _color_dist(rgb, bg_hex)
    near = int(((diff <= max(int(tol), 34)) & (core > 0)).sum()) if diff is not None else 0
    near_ratio = float(near) / float(max(1, core_n))

    if cons >= 0.90:
        mode, rec_tol = "chroma", 32
    elif cons >= 0.70:
        mode, rec_tol = "chroma", 40
    elif cons >= 0.55:
        mode, rec_tol = "chroma", 48
    else:
        mode, rec_tol = "grabcut", max(18, int(tol))

    sug = suggest_bg(rgb, ref, bg_hex)
    rec = {"mode": mode, "tol": int(rec_tol),
           "bg_hex": bg_hex if mode == "chroma" else "",
           "chroma": "auto" if mode == "chroma" else "off",
           "protect": True}
    if sug:
        rec["suggest_bg"] = "%s %s" % (sug["name"], sug["hex"])
        rec["bg_worth_switch"] = bool(sug.get("worth_switch"))

    risks = []
    if cons < 0.55:
        risks.append("四角背景一致度 %.2f 偏低（疑似渐变/场景），色度键不可靠，将走 GrabCut；"
                     "边缘容易留花边，建议重生成纯色底" % cons)
    elif cons < 0.80:
        risks.append("背景一致度 %.2f 中等，边缘可能有残留，色度键需放宽容差" % cons)
    if subj > 0.75:
        risks.append("主体占比 %.0f%% 过高（人物几乎顶满画面），背景留白不足，抠后贴边易被裁；"
                     "建议重生时人物小一点" % (subj * 100))
    if subj < 0.10:
        risks.append("主体占比仅 %.0f%%，可能人物过小或背景抢戏，抠图后主体会很小" % (subj * 100))
    if near_ratio > 0.10:
        risks.append("主体内部约 %.0f%% 像素与背景色 %s 接近，存在被误扣风险（v1.3 主体保护会自动回填，"
                     "但务必看对照图核对）" % (near_ratio * 100, bg_hex))
        if sug and sug.get("worth_switch"):
            risks.append("更稳的做法是换背景色重生：建议 --bg %s（%s），与主体色差更大"
                         % (sug["name"], sug["hex"]))
    if not risks:
        risks.append("无明显风险，可按推荐参数直接抠")

    rep.update({"mode": mode, "bg_hex": bg_hex, "bg_consistency": round(float(cons), 3),
                "bg_source": src, "subject_ratio": round(subj, 3), "bg_ratio": round(1 - subj, 3),
                "near_bg_ratio": round(near_ratio, 3), "core_px": core_n,
                "recommend": rec, "risks": risks})
    return rep


def print_analyze(rep):
    print("\n=== 抠前分析  %s (%s) ===" % (rep["file"], rep["size"]))
    if rep.get("mode") == "alpha-reuse":
        print("  模式        : alpha-reuse（自带透明通道，直接复用）")
    else:
        print("  背景一致度  : %.2f  (%s)   %s" % (
            rep["bg_consistency"], rep["bg_source"],
            "纯色可抠" if rep["bg_consistency"] >= 0.70 else
            ("勉强" if rep["bg_consistency"] >= 0.55 else "非纯色，别用色度键")))
        print("  背景色      : %s" % rep["bg_hex"])
        print("  主体占比估计: %.1f%%（背景 %.1f%%）" % (rep["subject_ratio"] * 100, rep["bg_ratio"] * 100))
        print("  主体内接近背景色像素: %.1f%%" % (rep["near_bg_ratio"] * 100))
        rc = rep["recommend"]
        print("  推荐参数    : --chroma %s --tol %d%s%s" % (
            rc["chroma"], rc["tol"],
            (" --bg-hex " + rc["bg_hex"]) if rc.get("bg_hex") else "",
            "" if rc.get("protect") else " --no-protect"))
        if rc.get("suggest_bg"):
            print("  备选背景色  : %s%s" % (rc["suggest_bg"],
                                        "（与主体色差更大，抠不干净时换它重生）" if rc.get("bg_worth_switch") else ""))
    for i, r in enumerate(rep["risks"], 1):
        print("  风险 %d      : %s" % (i, r))


# --------------------------------------------------------------------------- #
# 抠图
# --------------------------------------------------------------------------- #
def cut_one(path, tol=18, close_k=9, feather=1, chroma="auto", bg_hex="", protect=True,
            protect_radius=0, ref_fg=None):
    """返回 (out_img, info)。info 含 how / 分析信息 / 主体保护信息 / 参照前景。"""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit("读取失败: " + path)
    info = {"file": os.path.basename(path), "path": os.path.abspath(path), "how": ""}

    if has_alpha(img):
        info["how"] = "alpha-reuse"
        fg = (img[:, :, 3] > 127).astype(np.uint8)
        info["protect"] = {"protected": False, "kept_px": 0, "reason": "alpha-reuse 不抠"}
        info["ref_fg"] = _refine_mask(fg, close_k)
        info["bg_hex"] = bg_hex or ""
        return img, info

    rgb = img[:, :, :3]
    h, w = rgb.shape[:2]

    if ref_fg is None:
        ref_fg = _refine_mask(_grabcut_cut(rgb), close_k)
    info["ref_fg"] = ref_fg

    # 背景色优先级：--bg-hex > --chroma 指定色 > manifest(由调用方传入) > 四角采样
    target = ""
    if chroma != "off":
        if bg_hex:
            target = bg_hex
        elif chroma not in ("auto", ""):
            target = chroma
        else:
            target, consistent = sample_bg_hex(rgb)
            if consistent < 0.55:
                print("      [提示] 四角背景一致度 %.2f 偏低（疑似渐变/场景），跳色度键走 GrabCut" % consistent)
                target = ""
        if target:
            info["bg_hex"] = target

    fg, how = None, ""
    if target:
        m = _chroma_cut(rgb, target, tol=max(tol, 34))
        if m is not None:
            m = _refine_mask(m, close_k)
            if 0.02 <= m.mean() <= 0.98:
                fg, how = m, "chroma %s" % target
            # 主体保护：色度键 + GrabCut 交叉校验，落回主体内部被扣的像素
            if fg is not None and protect:
                fg2, pinfo = protect_subject(fg, ref_fg, radius=protect_radius or None)
                pinfo["reason"] = "色度键 vs GrabCut 交叉校验"
                info["protect"] = pinfo
                if pinfo["kept_px"] > 0:
                    how += " +protect(%dpx)" % pinfo["kept_px"]
                fg = _refine_mask(fg2, close_k)

    if fg is None:
        fg, how = ref_fg, "grabcut"
        info["protect"] = {"protected": False, "kept_px": 0, "reason": "GrabCut 主路线，无需交叉校验"}
    elif fg.mean() < 0.04 or fg.mean() > 0.97:
        # 兜底：四边 floodFill
        mask = np.zeros((h + 2, w + 2), np.uint8)
        seeds = []
        for x in range(0, w, max(1, w // 12)):
            seeds += [(x, 0), (x, h - 1)]
        for y in range(0, h, max(1, h // 12)):
            seeds += [(0, y), (w - 1, y)]
        bg = np.zeros((h, w), np.uint8)
        flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE
        for (x, y) in seeds:
            if bg[y, x]:
                continue
            m2 = mask.copy()
            cv2.floodFill(rgb.copy(), m2, (x, y), 255, (tol,) * 3, (tol,) * 3, flags)
            bg |= (m2[1:-1, 1:-1] > 0).astype(np.uint8)
        fg = _refine_mask((1 - bg).astype(np.uint8), close_k)
        if protect:
            fg, pinfo = protect_subject(fg, ref_fg, radius=protect_radius or None)
            pinfo["reason"] = "floodFill 兜底后再交叉校验"
            info["protect"] = pinfo
            fg = _refine_mask(fg, close_k)
        how = "floodfill-fallback"

    if fg.mean() < 0.02 or fg.mean() > 0.98:
        raise SystemExit("抠图失败（前景占比 %.3f）: %s" % (fg.mean(), path))

    alpha = (fg * 255).astype(np.uint8)
    if feather > 0:
        alpha = cv2.GaussianBlur(alpha, (feather * 2 + 1, feather * 2 + 1), 0)
        alpha = np.where(fg > 0, np.maximum(alpha, 180), alpha).astype(np.uint8)
    out = np.dstack([rgb, alpha])
    info["how"] = how
    info["fg"] = fg
    return out, info


# --------------------------------------------------------------------------- #
# 独立主体基准（校验不得用自身 mask 自证）
# --------------------------------------------------------------------------- #
def _grabcut_mask_alt(rgb, rect, inner, border, iters, max_side=900):
    """独立基准用的 GrabCut：初始化（矩形/内部正区/边界带）与主链 _grabcut_cut 不同，
    避免"自己判自己"。返回全尺寸 0/1 mask。"""
    h, w = rgb.shape[:2]
    scale = min(1.0, float(max_side) / float(max(h, w)))
    work = (cv2.resize(rgb, (max(1, int(w * scale)), max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA) if scale < 1 else rgb)
    hh, ww = work.shape[:2]
    gc = np.full((hh, ww), cv2.GC_PR_BGD, np.uint8)

    def _box(bx):
        x0, y0, x1, y1 = bx
        return (int(x0 * ww), int(y0 * hh),
                max(int(x0 * ww) + 1, int(x1 * ww)), max(int(y0 * hh) + 1, int(y1 * hh)))

    vx0, vy0, vx1, vy1 = _box(rect)
    gc[vy0:vy1, vx0:vx1] = cv2.GC_PR_FGD
    ix0, iy0, ix1, iy1 = _box(inner)
    gc[iy0:iy1, ix0:ix1] = cv2.GC_FGD
    d = max(1, int(min(hh, ww) * border))
    gc[:d, :] = cv2.GC_BGD
    gc[-d:, :] = cv2.GC_BGD
    gc[:, :d] = cv2.GC_BGD
    gc[:, -d:] = cv2.GC_BGD
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(work, gc, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    m = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    if scale < 1:
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
    return m


def _border_bg_subject(rgb, tol=45.0):
    """四边泛洪反推：与画幅四边连通且颜色相近的区域判为背景，剩下的就是主体。"""
    h, w = rgb.shape[:2]
    if min(h, w) < 8:
        return np.ones((h, w), np.uint8)
    flood = rgb.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    lo = up = (float(tol),) * 3
    step = max(8, min(h, w) // 40)
    seeds = ([(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)]
             + [(0, y) for y in range(0, h, step)] + [(w - 1, y) for y in range(0, h, step)])
    for sx, sy in seeds:
        if mask[sy + 1, sx + 1]:
            continue
        cv2.floodFill(flood, mask, (sx, sy), (0, 0, 0), lo, up, flags)
    return (1 - (mask[1:-1, 1:-1] > 0).astype(np.uint8)).astype(np.uint8)


def baseline_subject(rgb, close_k=9, core_pct=0.05):
    """独立主体基准：不看 --chroma、也不用本次抠图结果，单独把主体估一遍。

    三路互不相同的估计：
      A) GrabCut 紧矩形初始化（内正区小、只把正中当确定前景）
      B) GrabCut 宽矩形初始化（几乎整幅当可能前景，靠边界带做确定背景）
      C) 四边泛洪反推（与画幅四边连通且颜色相近的算背景，剩下的是主体）
    约定：
      - agree = A ∩ B（两套 GrabCut 都认可的区域）→ "保守主体"，用于 keep_ratio 与 IoU；
                一致的判断比单路更不容易把背景算进主体，也绝不会把被吃掉的主体算成背景。
      - full  = A ∪ B ∪ C → "主体上界"，只用于对照图画参考轮廓（多保不错杀）。
      - core  = erode(agree, core_pct × 短边)，去掉轮廓模糊带后"必然属于主体"的区域。
    C 若退化为空/满幅（纹理复杂时很可能），自动丢弃，不参与 agree/full 的判定。
    """
    h, w = rgb.shape[:2]
    a_mask = _refine_mask(
        _grabcut_mask_alt(rgb, (0.10, 0.05, 0.90, 0.95), (0.25, 0.15, 0.75, 0.85), 0.012, 6), close_k)
    b_mask = _refine_mask(
        _grabcut_mask_alt(rgb, (0.03, 0.02, 0.97, 0.98), (0.35, 0.25, 0.65, 0.75), 0.006, 8), close_k)
    c_mask = _refine_mask(_border_bg_subject(rgb, 45.0), close_k)
    parts = {"grabcut_tight": a_mask, "grabcut_wide": b_mask}
    c_ratio = float((c_mask > 0).mean())
    c_usable = 0.05 < c_ratio < 0.95
    if c_usable:
        parts["border_flood"] = c_mask

    ab = (a_mask > 0) & (b_mask > 0)
    agree = ab.astype(np.uint8)
    if int(agree.sum()) < int(0.04 * h * w):          # 两路分歧到没有公共区，退回单路
        agree = ((a_mask > 0) | (b_mask > 0)).astype(np.uint8)
    full = np.zeros((h, w), np.uint8)
    for m in parts.values():
        full |= (m > 0).astype(np.uint8)
    full = _refine_mask(full, close_k)
    core = _erode(agree, max(3, int(min(h, w) * core_pct)))
    return {"full": full, "agree": agree, "core": core,
            "parts": {k: round(float((v > 0).mean()), 4) for k, v in parts.items()},
            "border_flood_usable": bool(c_usable)}


def _dent_series(v, side):
    """一条边界序列相对"外沿包络"（约 6% 高度滑动窗）的内向凹陷：返回 (最大, 平均) 像素。"""
    v = np.asarray(v, np.float32)
    idx = np.arange(v.size)
    ok = np.isfinite(v)
    if int(ok.sum()) < 4:
        return 0.0, 0.0, -1, 0.0
    filled = np.interp(idx, idx[ok], v[ok])
    k = max(11, int(filled.size * 0.06))
    k = int(min(k, max(5, (filled.size // 2) * 2 - 1)))
    if k % 2 == 0:                 # 必须奇数，否则 pad 后窗口数比原序列多 1
        k = max(5, k - 1)
    pad = np.pad(filled, (k // 2, k // 2), mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(pad, k)
    if side == "left":
        env = win.min(axis=1)
        d = filled - env          # 左边界越往右凹越可疑
    else:
        env = win.max(axis=1)
        d = env - filled          # 右边界越往左凹越可疑
    d = np.clip(d, 0.0, None)
    at = int(np.argmax(d))
    return float(d.max()), float(d.mean()), int(round(float(filled[at]))), float(d.sum())


def _contour_dent(fg):
    """轮廓削切嫌疑：逐行左右边界相对正常轮廓包络的最大内向凹陷 ÷ 主体高度。"""
    fg = (fg > 0).astype(np.uint8)
    ys, _ = np.where(fg > 0)
    if ys.size < 16:
        return {"max_px": 0.0, "mean_px": 0.0, "ratio": 0.0, "side": "-", "y": -1}
    y0, y1 = int(ys.min()), int(ys.max())
    bh = max(1, y1 - y0 + 1)
    L, R = [], []
    for y in range(y0, y1 + 1):
        xx = np.where(fg[y] > 0)[0]
        if xx.size:
            L.append(float(xx.min()))
            R.append(float(xx.max()))
        else:
            L.append(np.nan)
            R.append(np.nan)
    lmax, lmean, ly, larea = _dent_series(L, "left")
    rmax, rmean, ry, rarea = _dent_series(R, "right")
    if lmax >= rmax:
        side, mx, my, mean_, area = "左", lmax, ly, lmean, larea
    else:
        side, mx, my, mean_, area = "右", rmax, ry, rmean, rarea
    return {"max_px": round(mx, 1), "mean_px": round(mean_, 1),
            "ratio": round(mx / float(bh), 4), "side": side, "y": int(y0 + max(0, my)),
            "area_px": float(area)}


# --------------------------------------------------------------------------- #
# 抠后校验（八项指标，全部以独立主体基准为参照）
# --------------------------------------------------------------------------- #
def metrics_of(rgb, fg, bg_hex, ib):
    """keep_ratio / iou / hole_rate / edge_cut_ratio / comp2_ratio / dent_ratio /
    fg_ratio / edge_color_diff，一律对照独立主体基准 ib，禁止用自身 mask 自证。"""
    h, w = rgb.shape[:2]
    fg = (fg > 0).astype(np.uint8)
    bool_fg = fg > 0
    full = ib["full"] > 0
    core = ib["core"] > 0
    agree = (ib.get("agree") if ib.get("agree") is not None else ib["full"]) > 0

    core_n = int(core.sum())
    kept = int((bool_fg & core).sum())
    keep_ratio = float(kept) / float(max(1, core_n))
    inter = int((bool_fg & agree).sum())
    union = int((bool_fg | agree).sum())
    iou = float(inter) / float(max(1, union))

    filled = _fill_holes(fg)
    holes = int(((filled > 0) & (fg == 0)).sum())
    hole_rate = float(holes) / float(max(1, int(filled.sum())))

    fg_ratio = float(fg.mean())

    band = (fg > 0) & (_erode(fg, 2) == 0)
    band_n = int(band.sum())
    margin = max(2, int(min(h, w) * 0.012))
    zone = np.zeros((h, w), bool)
    zone[:margin, :] = True
    zone[-margin:, :] = True
    zone[:, :margin] = True
    zone[:, -margin:] = True
    edge_cut_px = int((band & zone).sum())
    edge_cut_ratio = float(edge_cut_px) / float(max(1, band_n))

    n_lab, _lab, stats, _cent = cv2.connectedComponentsWithStats(fg, 8)
    areas = sorted([int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n_lab)], reverse=True)
    comp2_ratio = (float(areas[1]) / float(max(1, areas[0]))) if len(areas) > 1 else 0.0

    dent = _contour_dent(fg)

    edge = None
    bg_used = ""
    if band_n > 0:
        # 背景色：优先用本次抠图实际使用的色值；chroma off 时没有色值，改从原图四角采样，
        # 否则边缘色差会恒为 0 而把所有图误判成 FAIL。
        tgt = bg_hex if (bg_hex and _parse_hex(bg_hex)) else ""
        if not tgt:
            tgt, _cons = sample_bg_hex(rgb)
        t = _parse_hex(tgt)
        if t:
            bg_used = tgt
            tb, tg, tr = t[2], t[1], t[0]
            bp = rgb[band].astype(np.float64)
            edge = float(np.sqrt(((bp - np.array([tb, tg, tr], np.float64)) ** 2).sum(axis=1)).mean())

    return {
        "keep_ratio": round(keep_ratio, 4),
        # 旧字段名保留，避免外部脚本读不到；语义已改为"相对独立基准的保留率"
        "subject_retention": round(keep_ratio, 4),
        "lost_core_px": int(core_n - kept),
        "core_px": core_n,
        "iou": round(iou, 4),
        "ib_fg_ratio": round(float(full.mean()), 4),
        "ib_agree_ratio": round(float(agree.mean()), 4),
        "lost_agree_px": int(max(0, int(agree.sum()) - int((bool_fg & agree).sum()))),
        "ib_parts": ib.get("parts", {}),
        "hole_rate": round(hole_rate, 4),
        "hole_px": holes,
        "edge_cut_ratio": round(edge_cut_ratio, 4),
        "edge_cut_px": edge_cut_px,
        "comp2_ratio": round(comp2_ratio, 4),
        "comp_count": max(0, n_lab - 1),
        "dent_ratio": dent["ratio"],
        "dent_px": dent["max_px"],
        "dent_side": dent["side"],
        "dent_y": dent["y"],
        "dent_area_px": int(round(dent.get("area_px", 0.0))),
        "dent_area_ratio": round(float(dent.get("area_px", 0.0)) / float(max(1, int(bool_fg.sum()))), 4),
        "fg_ratio": round(fg_ratio, 4),
        "edge_color_diff": None if edge is None else round(edge, 1),
        "edge_bg_hex": bg_used,
        "edge_px": band_n,
    }


def judge(m):
    """按阈值给 PASS/WARN/FAIL 与具体原因。"""
    status, notes = "PASS", []

    def worse(new):
        return new if STATUS_ORDER[new] > STATUS_ORDER[status] else status

    if m["keep_ratio"] < T_KEEP_WARN:
        status = "FAIL"
        notes.append("主体被吃掉：相对独立基准仅保住 %.1f%%（丢了 %d 像素），人物/衣服/配件被当背景扣掉了"
                     % (m["keep_ratio"] * 100, m["lost_core_px"]))
    elif m["keep_ratio"] < T_KEEP_PASS:
        status = worse("WARN")
        notes.append("主体保留率 %.1f%% 偏低，边缘或小部件可能有缺角（对照图确认）"
                     % (m["keep_ratio"] * 100))

    if m["iou"] < T_IOU_FAIL:
        status = "FAIL"
        notes.append("与独立基准 IoU 仅 %.2f（<%.2f）：轮廓和主体对不上，一边多抠一边漏抠"
                     % (m["iou"], T_IOU_FAIL))

    if m["edge_cut_ratio"] > T_EDGE_CUT_FAIL:
        status = "FAIL"
        notes.append("主体有 %.1f%% 的边缘像素贴在画幅四边（%d 像素），人被画幅切断了"
                     % (m["edge_cut_ratio"] * 100, m["edge_cut_px"]))
    elif m["edge_cut_ratio"] > T_EDGE_CUT_WARN:
        status = worse("WARN")
        notes.append("主体 %.1f%% 边缘贴画幅（%d 像素），构图偏满，可能被切边"
                     % (m["edge_cut_ratio"] * 100, m["edge_cut_px"]))

    if m["hole_rate"] > T_HOLE_WARN:
        status = "FAIL"
        notes.append("主体内部被掏空 %.1f%%（%d 像素），像衣服/脸被抠出洞"
                     % (m["hole_rate"] * 100, m["hole_px"]))
    elif m["hole_rate"] > T_HOLE_PASS:
        status = worse("WARN")
        notes.append("主体内部有 %.2f%% 孔洞（%d 像素），可能抠漏了配件/衣领"
                     % (m["hole_rate"] * 100, m["hole_px"]))

    if m["comp2_ratio"] > T_COMP2_FAIL:
        status = "FAIL"
        notes.append("主体断成多块：第二大连通域占最大块的 %.1f%%，手臂/配件被切掉了"
                     % (m["comp2_ratio"] * 100))
    elif m["comp2_ratio"] > T_COMP2_WARN:
        status = worse("WARN")
        notes.append("主体断裂：第二大连通域占 %.1f%%，有一小块与主体分开"
                     % (m["comp2_ratio"] * 100))

    deep_dent = (m["dent_ratio"] > T_DENT_HARD
                 and m.get("dent_area_ratio", 0.0) > T_DENT_AREA)
    if m["dent_ratio"] > T_DENT_FAIL or deep_dent:
        status = "FAIL"
        notes.append("轮廓%s侧凹陷达主体高度 %.0f%%（最深 %.0f 像素，y≈%d），缺口面积占主体 %.2f%%（%d 像素）："
                     "头发/衣领已被整块削掉，按红线 5 不许进游戏；请换 --bg 重生纯色底后重抠"
                     % (m["dent_side"], m["dent_ratio"] * 100, m["dent_px"], m["dent_y"],
                        m.get("dent_area_ratio", 0.0) * 100, m.get("dent_area_px", 0)))
    elif m["dent_ratio"] > T_DENT_WARN:
        status = worse("WARN")
        notes.append("轮廓%s侧凹陷达主体高度 %.0f%%（%.0f 像素，y≈%d），头发两侧/肩部衣领疑似被削，"
                     "抠图边界可能切进了主体内部（务必看对照图确认）"
                     % (m["dent_side"], m["dent_ratio"] * 100, m["dent_px"], m["dent_y"]))

    lo, hi = FG_RATIO_PASS
    wlo, whi = FG_RATIO_WARN
    if m["fg_ratio"] < wlo or m["fg_ratio"] > whi:
        status = "FAIL"
        notes.append("前景占比 %.1f%% 异常（%s）" % (
            m["fg_ratio"] * 100, "主体几乎被扣没" if m["fg_ratio"] < wlo else "背景没抠掉"))
    elif m["fg_ratio"] < lo or m["fg_ratio"] > hi:
        status = worse("WARN")
        notes.append("前景占比 %.1f%% 偏离常规区间 %.0f%%~%.0f%%"
                     % (m["fg_ratio"] * 100, lo * 100, hi * 100))

    edge = m.get("edge_color_diff")
    if edge is None:
        notes.append("无边带像素（前景过小或全透明），跳过边缘判定")
    elif edge < T_EDGE_WARN:
        status = "FAIL"
        notes.append("边缘色差仅 %.0f，边缘仍糊着背景色（紫边/白边），抠不干净" % edge)
    elif edge < T_EDGE_PASS:
        status = worse("WARN")
        notes.append("边缘色差 %.0f 偏低，边缘可能有轻微残留" % edge)

    if not notes:
        notes.append("八项指标均达标")
    return status, notes


# --------------------------------------------------------------------------- #
# 对照图
# --------------------------------------------------------------------------- #
def _checkerboard(h, w, cell=16):
    y = (np.arange(h) // cell)[:, None]
    x = (np.arange(w) // cell)[None, :]
    c = ((x + y) % 2).astype(np.uint8)
    board = np.where(c[:, :, None] == 1, 238, 205).astype(np.uint8)
    return np.dstack([board, board, board])


def _label(img, text, color=(255, 255, 255)):
    bar_h = 26
    bar = np.full((bar_h, img.shape[1], 3), 32, np.uint8)
    cv2.putText(bar, text, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def make_compare(rgb, out_img, info, save_path, title=""):
    """原图 | 抠图(棋盘底) | 校验叠加(红=主体被扣,青=回填) 三栏并排。"""
    fg = (out_img[:, :, 3] > 127).astype(np.uint8)
    alpha = out_img[:, :, 3:4].astype(np.float32) / 255.0
    board = _checkerboard(rgb.shape[0], rgb.shape[1])
    comp = (out_img[:, :, :3].astype(np.float32) * alpha + board.astype(np.float32) * (1 - alpha))
    comp = comp.astype(np.uint8)

    # 对照图的"主体被扣"必须相对独立基准算，否则会把自身 mask 漏掉的部分也涂成合格
    ib = info.get("ib") or {}
    base = ib.get("agree")
    if base is None and info.get("ref_fg") is not None:
        base = _erode((info["ref_fg"] > 0).astype(np.uint8), max(3, int(min(rgb.shape[:2]) * 0.02)))
    overlay = rgb.copy()
    lost_px = 0
    kept_px = 0
    if base is not None:
        if base.shape[:2] != fg.shape[:2]:
            base = cv2.resize(base.astype(np.uint8), (fg.shape[1], fg.shape[0]),
                              interpolation=cv2.INTER_NEAREST)
        lost = ((base > 0) & (fg == 0))
        lost_px = int(lost.sum())
        overlay[lost] = (0, 0, 255)
    if ib.get("agree") is not None:
        full = ib["agree"]
        if full.shape[:2] != fg.shape[:2]:
            full = cv2.resize(full.astype(np.uint8), (fg.shape[1], fg.shape[0]),
                              interpolation=cv2.INTER_NEAREST)
        cnts, _ = cv2.findContours((full > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, cnts, -1, (0, 255, 255), 2)   # 黄线=独立基准主体上界
    pinfo = info.get("protect") or {}
    kept_px = int(pinfo.get("kept_px") or 0)

    p1 = _label(rgb.copy(), "ORIGINAL  bg=%s" % (info.get("bg_hex") or "-"), (200, 220, 255))
    p2 = _label(comp, "CUTOUT  fg=%.1f%%  how=%s" % (fg.mean() * 100, info.get("how", "")), (200, 255, 200))
    p3 = _label(overlay, "CHECK  lost=%dpx  restore=%dpx" % (lost_px, kept_px), (255, 210, 210))
    sep = np.full((p1.shape[0], 8, 3), 255, np.uint8)
    row = np.hstack([p1, sep, p2, sep, p3])

    max_w = 1500
    if row.shape[1] > max_w:
        r = max_w / float(row.shape[1])
        row = cv2.resize(row, (max_w, max(1, int(row.shape[0] * r))), interpolation=cv2.INTER_AREA)
    if title:
        row = _label(row, title, (255, 255, 255))
    os.makedirs(os.path.dirname(os.path.abspath(save_path)) or ".", exist_ok=True)
    cv2.imwrite(save_path, row, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return save_path, lost_px, kept_px


def build_compare_sheet(rows, save_path, gap=6):
    """把多张对照图竖向拼成一张总对照图。"""
    rows = [r for r in rows if r is not None and getattr(r, "size", 0)]
    if not rows:
        return None
    width = max(r.shape[1] for r in rows)
    rows = [cv2.copyMakeBorder(r, 0, 0, 0, width - r.shape[1],
                               cv2.BORDER_CONSTANT, value=(255, 255, 255)) for r in rows]
    parts = []
    for r in rows:
        parts.append(r)
        parts.append(np.full((gap, width, 3), 255, np.uint8))
    sheet = np.vstack(parts[:-1])
    max_h = 12000
    if sheet.shape[0] > max_h:
        sheet = cv2.resize(sheet, (max(1, int(sheet.shape[1] * max_h / sheet.shape[0])), max_h),
                           interpolation=cv2.INTER_AREA)
    os.makedirs(os.path.dirname(os.path.abspath(save_path)) or ".", exist_ok=True)
    cv2.imwrite(save_path, sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
    return save_path


def normalize(imgs, canvas=(640, 800), pad_top=0.06, pad_bottom=0.03):
    """统一画布：所有人物的“头顶”与“脚底”对齐到同一基准，水平居中。"""
    CW, CH = canvas
    boxes = [bbox_of(im[:, :, 3]) for im in imgs]
    heights = [b[3] - b[1] for b in boxes if b]
    if not heights:
        return imgs
    target_h = int(CH * (1 - pad_top - pad_bottom))
    outs = []
    for im, b in zip(imgs, boxes):
        if not b:
            outs.append(np.zeros((CH, CW, 4), np.uint8))
            continue
        x0, y0, x1, y1 = b
        sub = im[y0:y1, x0:x1]
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


def bbox_of(alpha):
    ys, xs = np.where(alpha > 8)
    if len(ys) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def collect_files(src):
    single = os.path.isfile(src)
    if single:
        return [src], True
    files = [os.path.join(src, f) for f in sorted(os.listdir(src))
             if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    return files, False


def resolve_manifest_bg(files):
    """按 v1.2 约定读取 raw/manifest.json 的 bg.hex。"""
    if not files:
        return ""
    mp = os.path.join(os.path.dirname(os.path.abspath(files[0])), "manifest.json")
    if not os.path.exists(mp):
        return ""
    try:
        return ((json.load(open(mp, encoding="utf-8")) or {}).get("bg") or {}).get("hex", "") or ""
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser(
        description="表情图抠图 / 统一画布 / 抠前分析 / 抠后校验（v%s）" % VERSION)
    ap.add_argument("--in", dest="src", required=True, help="输入图片或目录")
    ap.add_argument("--out", dest="dst", default="", help="输出目录（--analyze 可省略）")
    ap.add_argument("--tol", type=int, default=18, help="颜色容差（按 --analyze 推荐值给，别盲调）")
    ap.add_argument("--close", type=int, default=9, help="闭运算核大小，补断口")
    ap.add_argument("--feather", type=int, default=1, help="边缘羽化像素")
    ap.add_argument("--normalize", action="store_true", help="统一画布（推荐开启，避免游戏内换表情跳动）")
    ap.add_argument("--canvas", default="640x800")
    ap.add_argument("--chroma", default="auto",
                    help="色度键背景色：auto=读 manifest.json 的 bg.hex、缺失则四角采样；"
                         "也可直接给 #RRGGBB；off=只用 GrabCut")
    ap.add_argument("--bg-hex", default="", help="直接指定背景色 #RRGGBB（优先于 --chroma）")
    ap.add_argument("--analyze", action="store_true",
                    help="[v1.3] 只分析不出图：背景一致度/背景色/主体占比/推荐参数/风险")
    ap.add_argument("--analyze-report", default="", help="分析结果 JSON 路径（默认 <out>/cutout.analyze.json）")
    ap.add_argument("--verify", action="store_true",
                    help="[v1.3] 抠后逐张比对，产出 cutout.report.json；有 FAIL 时退出码 2")
    ap.add_argument("--report", default="", help="校验报告路径（默认 <out>/cutout.report.json）")
    ap.add_argument("--compare", action="store_true",
                    help="[v1.3] 生成原图与抠图结果的并排对照图（默认 <out>/compare/）")
    ap.add_argument("--compare-dir", default="", help="对照图输出目录（默认 <out>/compare/）")
    ap.add_argument("--compare-only", action="store_true",
                    help="只重出对照图：读 --out 目录里同名已抠好的图与原图比对")
    ap.add_argument("--no-protect", action="store_true",
                    help="[v1.3] 关闭默认开启的主体保护（仅在明确知道副作用时使用）")
    ap.add_argument("--protect-radius", type=int, default=0,
                    help="主体保护核心区腐蚀半径，0=按图像短边 2.5%% 自动")
    a = ap.parse_args()

    if not a.analyze and not a.dst:
        ap.error("除 --analyze 外必须给 --out（抠图结果写哪里）")

    try:
        CW, CH = [int(x) for x in a.canvas.lower().split("x")]
    except Exception:
        ap.error("--canvas 需形如 640x800")
    if a.compare and not a.compare_dir and a.dst:
        a.compare_dir = os.path.join(a.dst, "compare")

    files, single = collect_files(a.src)
    if not files:
        raise SystemExit("没有输入图片: " + a.src)
    if a.dst and not single:
        os.makedirs(a.dst, exist_ok=True)

    # 背景色：--bg-hex 优先，其次 manifest（色度键 auto）
    bg_hex = a.bg_hex.strip()
    if not bg_hex and a.chroma in ("auto", ""):
        bg_hex = resolve_manifest_bg(files)
        if bg_hex:
            print("  背景色取自 manifest: %s（色度键模式）" % bg_hex)
        else:
            print("  未找到 manifest 中的背景色，改为四角采样自动识别")

    # ---------------- 抠前分析 ----------------
    if a.analyze:
        recs = []
        for p in files:
            img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if img is None:
                print("  [SKIP] 读取失败: %s" % p)
                continue
            rep = analyze_image(p, img, bg_hex_pref=bg_hex, tol=a.tol)
            recs.append(rep)
            print_analyze(rep)
        out = a.analyze_report
        if not out:
            # 未给 --out 时写到输入目录旁边，避免把报告丢到当前工作目录
            base_dir = os.path.dirname(os.path.abspath(files[0])) if files else "."
            out = os.path.join(a.dst or base_dir, "cutout.analyze.json")
        if out and recs:
            os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
            json.dump({"version": VERSION, "items": recs},
                      open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print("\n  分析结果已写入: %s" % os.path.abspath(out))
        print("\n  下一步：按上面的推荐参数抠图（禁止盲调 tol），例：")
        rc = next((r["recommend"] for r in recs if r.get("recommend")), None)
        if rc:
            print("    python cutout.py --in %s --out %s --normalize --chroma %s --tol %d%s --verify --compare"
                  % (a.src, a.dst or "assets/", rc.get("chroma", "auto"), rc.get("tol", 32),
                     (" --bg-hex " + rc["bg_hex"]) if rc.get("bg_hex") else ""))
        return

    # ---------------- compare-only：只重出对照图 ----------------
    if a.compare_only:
        if not a.dst:
            ap.error("--compare-only 必须给 --out（已抠图所在目录）")
        rows = []
        for p in files:
            name = os.path.splitext(os.path.basename(p))[0] + ".png"
            cut = os.path.join(a.dst, name)
            if not os.path.exists(cut):
                print("  [SKIP] 找不到对应的抠图结果: %s" % cut)
                continue
            orig = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            out = cv2.imread(cut, cv2.IMREAD_UNCHANGED)
            if orig is None or out is None or out.shape[2] != 4:
                print("  [SKIP] 图像不可用: %s" % name)
                continue
            rgb = orig[:, :, :3]
            if out.shape[:2] != rgb.shape[:2]:
                out = cv2.resize(out, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_AREA)
            info = {"how": "compare-only", "bg_hex": bg_hex,
                    "ib": baseline_subject(rgb, a.close),
                    "ref_fg": _refine_mask(_grabcut_cut(rgb), a.close) if not has_alpha(orig) else
                    (orig[:, :, 3] > 127).astype(np.uint8)}
            sp, lost, kept = make_compare(rgb, out, info,
                                          os.path.join(a.compare_dir or os.path.join(a.dst, "compare"),
                                                       name.replace(".png", ".compare.jpg")),
                                          title=os.path.basename(p))
            print("  %-28s 对照图 -> %s（lost=%dpx）" % (name, sp, lost))
            rows.append(cv2.imread(sp))
        sheet = build_compare_sheet(rows, os.path.join(a.compare_dir or os.path.join(a.dst, "compare"),
                                                      "compare.sheet.jpg"))
        if sheet:
            print("  总对照图: %s" % sheet)
        return

    # ---------------- 抠图 + 校验 + 对照 ----------------
    imgs, infos, names = [], [], []
    for p in files:
        try:
            im, info = cut_one(p, a.tol, a.close, a.feather, a.chroma, bg_hex,
                               protect=not a.no_protect, protect_radius=a.protect_radius)
        except SystemExit as e:
            print("  [SKIP] %s" % e)
            continue
        imgs.append(im)
        infos.append(info)
        names.append(os.path.basename(p))
        pinfo = info.get("protect") or {}
        print("  %-28s %-22s %dx%d%s" % (
            os.path.basename(p), info.get("how", ""), im.shape[1], im.shape[0],
            "  回填%dpx" % pinfo.get("kept_px", 0) if pinfo.get("kept_px") else ""))

    if not imgs:
        raise SystemExit("全部图片抠图失败，检查输入目录是否为表情原图")

    # 校验（用抠图前的原图比对，必须与输出同尺寸）
    report_items = []
    for p, im, info in zip(names, imgs, infos):
        orig = cv2.imread(info["path"], cv2.IMREAD_UNCHANGED)
        rgb = orig[:, :, :3]
        fg = (im[:, :, 3] > 127).astype(np.uint8) if im.shape[:2] == rgb.shape[:2] else None
        if fg is None:
            rgb = cv2.resize(rgb, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_AREA)
            fg = (im[:, :, 3] > 127).astype(np.uint8)
        # 独立主体基准：只在校验时单独估一遍，与本次抠图路径/参数完全无关
        ib = baseline_subject(rgb, a.close)
        info["ib"] = ib
        m = metrics_of(rgb, fg, info.get("bg_hex") or bg_hex, ib)
        st, notes = judge(m)
        report_items.append({"file": p, "key": os.path.splitext(p)[0], "how": info.get("how", ""),
                             "bg_hex": info.get("bg_hex") or bg_hex, "status": st,
                             "metrics": m, "notes": notes,
                             "baseline": {"fg_ratio": m["ib_fg_ratio"], "parts": m["ib_parts"]},
                             "protect": {k: v for k, v in (info.get("protect") or {}).items()}})
        print("  校验 %-24s %-5s 保留%.1f%% IoU%.2f 孔洞%.2f%% 凹陷%.2f 前景%.1f%% 边缘%s" % (
            os.path.basename(p), st, m["keep_ratio"] * 100, m["iou"], m["hole_rate"] * 100,
            m["dent_ratio"], m["fg_ratio"] * 100,
            "-" if m["edge_color_diff"] is None else "%.0f" % m["edge_color_diff"]))

    # 对照图（在归一化之前做，保证与原图同尺寸）
    rows, compare_paths = [], []
    if a.compare:
        for p, im, info in zip(names, imgs, infos):
            orig = cv2.imread(info["path"], cv2.IMREAD_UNCHANGED)[:, :, :3]
            if im.shape[:2] != orig.shape[:2]:
                im2 = cv2.resize(im, (orig.shape[1], orig.shape[0]), interpolation=cv2.INTER_AREA)
            else:
                im2 = im
            cdir = a.compare_dir or os.path.join(a.dst, "compare")
            sp, lost, kept = make_compare(
                orig, im2, info,
                os.path.join(cdir, os.path.basename(p).rsplit(".", 1)[0] + ".compare.jpg"),
                title=os.path.basename(p))
            compare_paths.append(sp)
            rows.append(cv2.imread(sp))
        sheet = build_compare_sheet(rows, os.path.join(a.compare_dir or os.path.join(a.dst, "compare"),
                                                      "compare.sheet.jpg"))
        if sheet:
            print("  总对照图: %s" % sheet)

    if a.normalize and len(imgs) > 1:
        imgs = normalize(imgs, (CW, CH))
        print("  已统一画布 %dx%d" % (CW, CH))

    for im, nm in zip(imgs, names):
        base = os.path.splitext(nm)[0] + ".png"
        out = a.dst if single else os.path.join(a.dst, base)
        cv2.imwrite(out, im)
        print("  -> %s (%d 字节)" % (out, os.path.getsize(out)))

    # 报告
    if a.verify:
        cnt = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for it in report_items:
            cnt[it["status"]] = cnt.get(it["status"], 0) + 1
        rework = [it["key"] for it in report_items if it["status"] == "FAIL"]
        warn_keys = [it["key"] for it in report_items if it["status"] == "WARN"]
        rep = {"version": VERSION,
               "generated": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
               "verify_basis": "independent baseline_subject = GrabCut(紧矩形初始化) ∩ GrabCut(宽矩形初始化) = agree 保守主体"
                    " (用于 keep_ratio/iou)，四边泛洪反推只并入 full 上界；core = erode(agree, 5%×短边)；"
                    "全程不看 --chroma、不读本次 mask —— 禁止用自身 mask 自证",
               "thresholds": {"keep_ratio": {"pass": T_KEEP_PASS, "fail": T_KEEP_WARN},
                              "iou_fail": T_IOU_FAIL,
                              "hole_rate": {"warn": T_HOLE_PASS, "fail": T_HOLE_WARN},
                              "edge_cut_ratio": {"warn": T_EDGE_CUT_WARN, "fail": T_EDGE_CUT_FAIL},
                              "comp2_ratio": {"warn": T_COMP2_WARN, "fail": T_COMP2_FAIL},
                              "dent_ratio": {"warn": T_DENT_WARN, "fail": T_DENT_FAIL,
                                             "hard": T_DENT_HARD, "area_fail": T_DENT_AREA},
                              "fg_ratio_pass": list(FG_RATIO_PASS),
                              "fg_ratio_warn": list(FG_RATIO_WARN),
                              "edge_color_diff": {"pass": T_EDGE_PASS, "fail": T_EDGE_WARN}},
               "params": {"tol": a.tol, "close": a.close, "feather": a.feather,
                          "chroma": a.chroma, "bg_hex": bg_hex, "protect": not a.no_protect,
                          "normalize": bool(a.normalize), "canvas": a.canvas},
               "summary": {"total": len(report_items), "pass": cnt["PASS"], "warn": cnt["WARN"],
                           "fail": cnt["FAIL"], "rework": rework, "warn_keys": warn_keys},
               "compare_sheet": os.path.abspath(os.path.join(a.compare_dir, "compare.sheet.jpg"))
               if (a.compare and a.compare_dir) else "",
               "items": report_items}
        rp = a.report or (os.path.join(a.dst, "cutout.report.json") if a.dst else "cutout.report.json")
        os.makedirs(os.path.dirname(os.path.abspath(rp)) or ".", exist_ok=True)
        json.dump(rep, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("\n  校验报告: %s" % os.path.abspath(rp))
        print("  PASS %d / WARN %d / FAIL %d（共 %d 张）"
              % (cnt["PASS"], cnt["WARN"], cnt["FAIL"], len(report_items)))
        for it in report_items:
            if it["status"] != "PASS":
                print("  [%s] %s: %s" % (it["status"], it["file"], "；".join(it["notes"])))
        if rework:
            keys = ",".join(os.path.splitext(os.path.basename(k))[0] for k in rework)
            print("\n  [返工] %d 张不合格，先把这些 key 回去重生（换纯色底/换背景色），"
                  "别在这里硬调 tol：" % len(rework))
            print("    python gen_expressions.py --photo <照片> --out raw/ --only %s --bg magenta" % keys)
            sys.exit(2)


if __name__ == "__main__":
    main()

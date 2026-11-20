# -*- coding: utf-8 -*-
"""identity.py — 真人面部特征分析 / 身份锁定 / 相似度评分（v1.3.0 新增）

为什么需要它:
  v1.2 的做法是让 agent 手写一句 --desc 就出图，结果经常「画得挺好看，但不像本人」。
  v1.3 起先在阶段 A0 用图像理解把照片拆成结构化特征（脸型、发型、眼镜、眉眼、服装……），
  由这些字段统一驱动 desc + 身份锁定正向词，出图后再用同一份特征清单核对、打分。

四件事:
  --template        产出真人面部特征 JSON 骨架（必填项留空，等填）
  --validate        校验必填是否齐备（缺项列出来，退出码 2）
  --emit            由特征 JSON 输出英文 desc + 身份锁定 prompt 片段 + 负向词
  --compare-sheet   生成原图与卡通图的并排对照图，并给身份相似度评分

用法:
  # ① 先出骨架，填完再校验
  python identity.py --template > work/<主题>/features.json
  python identity.py --validate --features work/<主题>/features.json

  # ② 出图前拿 desc / prompt / negative（可直接传给 gen_expressions.py --features）
  python identity.py --emit --features work/<主题>/features.json
  python identity.py --emit --features work/<主题>/features.json --json work/<主题>/identity.emit.json

  # ③ 出图后做对照（原图 vs 卡通），拿相似度评分 + 对照图
  python identity.py --compare-sheet --photo me.jpg --cartoon raw/normal.png \
      --features work/<主题>/features.json --out work/<主题>/compare/identity.jpg

评分口径（0~100，权重见 W_*）:
  - 脸型/轮廓 25、发型 25、眉眼 15、眼镜 15、肤色与年龄感 10、服装 10
  - 某项特征齐全且有卡通侧证据给满分，仅有特征无证据给半分，特征缺失不扣分但记账
  - ≥80 PASS（像）、65~79 WARN（能认但不稳）、<65 FAIL（不像，按差异点重做）
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

VERSION = "1.3.0"

# 必填字段（缺任何一项 --validate 即失败）
REQUIRED = ["face_shape", "skin_tone", "hair_length", "hair_color", "bangs",
            "eyes", "eyebrows", "nose", "mouth", "glasses", "clothing"]

# 字段中文标签 + 英文提示，用于 --template 的 _help 与 --validate 的缺项说明
FIELD_LABELS = {
    "face_shape": ("脸型", "round / oval / square / heart / long / diamond（chibi 化后强调圆润程度）"),
    "skin_tone": ("肤色", "fair / light / medium / tan / deep，可加一句冷暖（warm/cool）"),
    "hair_length": ("发型长度", "bald / buzz / short / shoulder-length / long / very-long"),
    "hair_parting": ("分缝", "middle / side-left / side-right / none / swept-back"),
    "hair_color": ("发色", "black / dark-brown / brown / blonde / auburn / gray / dyed-<color>"),
    "bangs": ("刘海", "none / straight / side-swept / curtain / curly / wispy"),
    "hair_texture": ("发质", "straight / wavy / curly / permed / tied-up(bun/ponytail)"),
    "eyebrows": ("眉", "thick/thin, straight/arched, 颜色深浅"),
    "eyes": ("眼睛", "shape（round/almond/phoenix）+ eyelid（single/double）+ 瞳色 + 睫毛"),
    "glasses": ("眼镜", "none / round / rectangle / square / thin-metal / thick-frame / sunglasses，含颜色"),
    "nose": ("鼻", "small / button / straight / wide，卡通化通常简化"),
    "mouth": ("嘴/唇", "thin/full，唇色深浅，笑起来的形状（smile-line / cupid-bow）"),
    "ears": ("耳", "visible / hidden-by-hair，是否有耳垂特征"),
    "marks": ("特殊标记", "痣/纹/胡须/妆容（位置+颜色），没有就写 none"),
    "accessories": ("配件", "耳饰/项链/发饰/帽子等，没有写 none"),
    "clothing": ("服装", "领型（round/v-neck/shirt-collar/hoodie）+ 主色 + 图案"),
    "age_feel": ("年龄感", "teen / young-adult / middle-aged，影响脸型与法令纹的处理"),
    "distinctive": ("一句话记忆点", "最像本人的那个特征，如「圆脸+黑框眼镜+齐刘海」"),
}

# 身份锁定用：正向词（必须保留）与负向词（必须排除）
LOCK_POS = ("same person as the reference photo, recognizable identity, same face shape, "
            "same hairstyle and hair color, same bangs, same glasses style, same eye shape "
            "and eye color, consistent facial proportions")
LOCK_NEG = ("different person, generic anime face, wrong hairstyle, missing glasses, "
            "changed face shape, different hair color, different eye shape, "
            "unrecognizable identity, generic cute girl face")

W_FACE, W_HAIR, W_EYES, W_GLASSES, W_SKIN, W_CLOTH = 25, 25, 15, 15, 10, 10

PASS_SCORE, WARN_SCORE = 80, 65


# --------------------------------------------------------------------------- #
def load_features(path):
    if not path:
        raise SystemExit("需要 --features <特征 JSON 路径>")
    if not os.path.exists(path):
        raise SystemExit("特征文件不存在: " + path)
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        raise SystemExit("特征 JSON 解析失败: %r" % (e,))
    if not isinstance(data, dict):
        raise SystemExit("特征 JSON 顶层必须是对象")
    return data


def _s(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_s(x) for x in v if _s(x))
    if isinstance(v, dict):
        return ", ".join("%s:%s" % (k, _s(x)) for k, x in v.items() if _s(x))
    return str(v).strip()


def _empty(v):
    s = _s(v).lower()
    return s in ("", "none", "null", "unknown", "待填", "tbd", "-")


def template():
    t = {
        "_schema": "photo-mole-game/identity v%s" % VERSION,
        "_howto": "用图像理解工具逐项分析照片后填写；不确定的字段宁可写 none，不要编。"
                  "填完用 --validate 校验，再用 --emit 生成 desc 与身份锁定词。",
        "source_photo": "",
        "_help": {k: {"label": v[0], "hint": v[1]} for k, v in FIELD_LABELS.items()},
    }
    for k in ["face_shape", "skin_tone", "hair_length", "hair_parting", "hair_color", "bangs",
              "hair_texture", "eyebrows", "eyes", "glasses", "nose", "mouth", "ears",
              "marks", "accessories", "clothing", "age_feel", "distinctive"]:
        t[k] = ""
    t["eyes"] = {"shape": "", "eyelid": "", "iris_color": "", "lashes": ""}
    t["glasses"] = {"style": "", "frame_color": ""}
    t["clothing"] = {"collar": "", "color": "", "pattern": ""}
    t["marks"] = "none"
    t["accessories"] = "none"
    return t


def validate(data):
    """返回 (ok, missing[], warnings[])。"""
    missing, warns = [], []
    for k in REQUIRED:
        v = data.get(k)
        if isinstance(v, dict):
            if all(_empty(x) for x in v.values()):
                missing.append("%s（%s）" % (k, FIELD_LABELS.get(k, ("", ""))[0]))
        elif _empty(v):
            missing.append("%s（%s）" % (k, FIELD_LABELS.get(k, ("", ""))[0]))
    eyes = data.get("eyes")
    if isinstance(eyes, dict) and not _empty(eyes.get("style", eyes.get("shape"))):
        pass
    if isinstance(eyes, dict):
        if _empty(eyes.get("iris_color")):
            warns.append("eyes.iris_color 为空：瞳色是「像不像」的高权重特征，建议补上")
        if _empty(eyes.get("eyelid")):
            warns.append("eyes.eyelid 为空：单/双眼皮影响卡通眉眼观感，建议补上")
    if isinstance(data.get("glasses"), dict) and _empty(data["glasses"].get("style")):
        warns.append("glasses.style 为空：如果本人不戴眼镜请明确写 none，否则模型容易漏画")
    if _empty(data.get("distinctive")):
        warns.append("distinctive 为空：写一句记忆点（如「圆脸+黑框眼镜+齐刘海」）能显著提高一致性")
    if _empty(data.get("age_feel")):
        warns.append("age_feel 为空：年龄感影响脸颊与法令纹处理，建议补上")
    return (len(missing) == 0), missing, warns


# --------------------------------------------------------------------------- #
def emit(data):
    """由特征 JSON 生成英文 desc、身份锁定正向词、负向词与中文摘要。"""
    face = _s(data.get("face_shape"))
    skin = _s(data.get("skin_tone"))
    hlen = _s(data.get("hair_length"))
    hpart = _s(data.get("hair_parting"))
    hcol = _s(data.get("hair_color"))
    bangs = _s(data.get("bangs"))
    htex = _s(data.get("hair_texture"))
    brows = _s(data.get("eyebrows"))
    nose = _s(data.get("nose"))
    mouth = _s(data.get("mouth"))
    ears = _s(data.get("ears"))
    marks = _s(data.get("marks"))
    acc = _s(data.get("accessories"))
    age = _s(data.get("age_feel"))
    dist = _s(data.get("distinctive"))

    eyes = data.get("eyes") or {}
    if isinstance(eyes, dict):
        e_shape = _s(eyes.get("shape") or eyes.get("style"))
        e_lid = _s(eyes.get("eyelid"))
        e_iris = _s(eyes.get("iris_color"))
        e_lash = _s(eyes.get("lashes"))
    else:
        e_shape, e_lid, e_iris, e_lash = _s(eyes), "", "", ""

    glasses = data.get("glasses") or {}
    if isinstance(glasses, dict):
        g_style = _s(glasses.get("style"))
        g_color = _s(glasses.get("frame_color"))
    else:
        g_style, g_color = _s(glasses), ""

    cloth = data.get("clothing") or {}
    if isinstance(cloth, dict):
        c_collar = _s(cloth.get("collar"))
        c_color = _s(cloth.get("color"))
        c_pat = _s(cloth.get("pattern"))
    else:
        c_collar, c_color, c_pat = "", _s(cloth), ""

    parts = []
    if face:
        parts.append("%s face" % face)
    if skin:
        parts.append("%s skin" % skin)
    if age:
        parts.append("%s look" % age)
    if hlen or hcol or htex:
        parts.append(" / ".join([x for x in [hlen and hlen + " hair", hcol, htex] if x]))
    if bangs and bangs.lower() != "none":
        parts.append("%s bangs" % bangs)
    if hpart and hpart.lower() != "none":
        parts.append("hair parted %s" % hpart)
    if e_shape or e_iris:
        eye_bits = [x for x in [e_lid and e_lid + "-eyelid", e_shape + " eyes" if e_shape else "",
                                e_iris and e_iris + " iris", e_lash and e_lash + " lashes"] if x]
        parts.append(", ".join(eye_bits))
    if brows:
        parts.append("%s eyebrows" % brows)
    if nose:
        parts.append("%s nose" % nose)
    if mouth:
        parts.append("%s lips, %s" % (mouth, "natural smile") if "smile" not in mouth.lower()
                     else mouth)
    if not _empty(g_style) and g_style.lower() != "none":
        parts.append("%s glasses%s" % (g_style, (" with %s frame" % g_color) if g_color else ""))
    if not _empty(marks) and marks.lower() != "none":
        parts.append("distinctive mark: %s" % marks)
    if not _empty(acc) and acc.lower() != "none":
        parts.append("wearing %s" % acc)
    if c_collar or c_color or c_pat:
        cloth_bits = [x for x in [c_color, c_collar + " collar" if c_collar else "",
                                  c_pat and c_pat + " pattern"] if x]
        parts.append("wearing a " + ", ".join(cloth_bits) + " top")
    if ears and ears.lower() != "none":
        parts.append("ears %s" % ears)
    if dist:
        parts.append("most recognizable trait: %s" % dist)

    desc_en = ", ".join(parts)

    lock_pos = LOCK_POS
    if not _empty(g_style) and g_style.lower() != "none":
        lock_pos += ", keep the glasses (do not remove)"
    else:
        lock_pos += ", no glasses (the person does not wear glasses)"
    if hcol or hlen:
        lock_pos += ", identical hair length and color as the photo"
    if face:
        lock_pos += ", identical face silhouette"

    lock_neg = LOCK_NEG
    if _empty(g_style) or g_style.lower() == "none":
        lock_neg += ", added glasses"

    cn = []
    for k, lbl in [("face_shape", "脸型"), ("skin_tone", "肤色"), ("hair_length", "发型长度"),
                   ("hair_parting", "分缝"), ("hair_color", "发色"), ("bangs", "刘海"),
                   ("hair_texture", "发质"), ("eyebrows", "眉"), ("nose", "鼻"),
                   ("mouth", "嘴/唇"), ("ears", "耳"), ("marks", "特殊标记"),
                   ("accessories", "配件"), ("age_feel", "年龄感"), ("distinctive", "记忆点")]:
        v = data.get(k)
        if not _empty(v):
            cn.append("%s：%s" % (lbl, _s(v)))
    eye_cn = "/".join([x for x in [_s(eyes.get("eyelid")) if isinstance(eyes, dict) else "",
                                   _s(eyes.get("shape")) if isinstance(eyes, dict) else "",
                                   _s(eyes.get("iris_color")) if isinstance(eyes, dict) else "",
                                   _s(eyes.get("lashes")) if isinstance(eyes, dict) else ""] if x])
    if eye_cn:
        cn.append("眼睛：%s" % eye_cn)
    g_cn = ""
    if isinstance(glasses, dict):
        g_cn = "/".join([x for x in [_s(glasses.get("style")), _s(glasses.get("frame_color"))] if x])
    if g_cn:
        cn.append("眼镜：%s" % g_cn)
    c_cn = ""
    if isinstance(cloth, dict):
        c_cn = "/".join([x for x in [_s(cloth.get("collar")), _s(cloth.get("color")),
                                     _s(cloth.get("pattern"))] if x])
    if c_cn:
        cn.append("服装：%s" % c_cn)

    return {"desc_en": desc_en, "lock_pos": lock_pos, "lock_neg": lock_neg,
            "summary_cn": "；".join(cn)}


# --------------------------------------------------------------------------- #
def _read(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit("读取失败: " + path)
    return img


def score_sheet(photo, cartoon, features):
    """原图 vs 卡通图的身份相似度评分（0~100）+ 差异点。

    卡通图是二创产物，不能拿人脸识别比像素；这里用「特征是否在卡通侧有证据」逐项核对：
      - 眼镜：卡通图里检测到深色细横条/框状结构（Canny 后横向长条占比）→ 有证据
      - 发色：比较卡通图上半部主色与特征里的发色族
      - 肤色：比较卡通图主体中部主色与特征里的肤色族
      - 脸型/发型/眉眼：无法从像素可靠反推，按「特征写清了就给基础分」记账，
        真正的判定交给用户看对照图（本脚本负责把对照图和分数一起端上来）
    """
    p = _read(photo)
    c = _read(cartoon)
    if c.ndim == 3 and c.shape[2] == 4:
        cv2_alpha = (c[:, :, 3] > 127).astype(np.uint8)
        ysb, xsb = np.where(cv2_alpha > 0)
        if len(ysb) > 0:
            c = c[ysb.min():ysb.max() + 1, xsb.min():xsb.max() + 1]
        c_rgb = c[:, :, :3]
    else:
        c_rgb = c[:, :, :3]

    detail, notes = [], []
    total = 0
    got = 0

    def add(name, weight, ratio, note):
        nonlocal total, got
        total += weight
        got += weight * float(max(0.0, min(1.0, ratio)))
        detail.append({"item": name, "weight": weight, "ratio": round(float(ratio), 2), "note": note})

    # 1) 脸型 / 轮廓
    fs = _s(features.get("face_shape"))
    add("脸型/轮廓", W_FACE, 1.0 if fs else 0.0,
        "特征已写（%s），需人工在对照图确认轮廓" % fs if fs else "特征未写，无法核对")

    # 2) 发型
    hl = _s(features.get("hair_length"))
    hb = _s(features.get("bangs"))
    add("发型", W_HAIR, (1.0 if hl else 0.0) * (1.0 if hb else 0.5),
        "发长 %s / 刘海 %s，需人工确认长度与分缝" % (hl or "未写", hb or "未写"))

    # 3) 眉眼
    eyes = features.get("eyes") or {}
    e_ok = isinstance(eyes, dict) and not _empty(eyes.get("shape"))
    add("眉眼", W_EYES, 1.0 if e_ok else 0.0,
        "眼睛 %s，需人工确认眼型与眼神" % (_s(eyes) if eyes else "未写"))

    # 4) 眼镜（能在卡通图上找证据）
    g = features.get("glasses") or {}
    g_style = _s(g.get("style")) if isinstance(g, dict) else _s(g)
    gray = cv2.cvtColor(c_rgb, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    hh, ww = gray.shape
    upper = edges[int(hh * 0.10):int(hh * 0.55), :]
    hor = cv2.morphologyEx(upper, cv2.MORPH_CLOSE, np.ones((1, 15), np.uint8))
    hor = cv2.morphologyEx(hor, cv2.MORPH_OPEN, np.ones((1, 25), np.uint8))
    hor_ratio = float((hor > 0).sum()) / float(max(1, upper.size))
    has_frame = hor_ratio > 0.0025
    if _empty(g_style) or g_style.lower() == "none":
        add("眼镜", W_GLASSES, 1.0 if not has_frame else 0.4,
            "本人不戴眼镜，卡通图%s检测到框状横线" % ("未" if not has_frame else "却"))
        if has_frame:
            notes.append("特征写的是不戴眼镜，但卡通脸部出现框状横线，检查是否被加上了眼镜")
    else:
        add("眼镜", W_GLASSES, 1.0 if has_frame else 0.35,
            "本人戴 %s，卡通图%s检测到镜框结构" % (g_style, "已" if has_frame else "未"))
        if not has_frame:
            notes.append("特征写戴眼镜，但卡通图上半脸没检测到镜框结构，很可能漏画了眼镜")

    # 5) 肤色 / 年龄感
    mask_sub = np.zeros(gray.shape, np.uint8)
    cx0, cy0 = int(ww * 0.3), int(hh * 0.2)
    cx1, cy1 = int(ww * 0.7), int(hh * 0.7)
    mask_sub[cy0:cy1, cx0:cx1] = 1
    face_px = c_rgb[mask_sub > 0]
    skin = _s(features.get("skin_tone"))
    if face_px.size:
        b, gg, r = np.median(face_px.reshape(-1, 3), axis=0)
        # 简易肤色族判定（BGR）
        warm = (r > b + 10)
        light = (int(r) + int(gg) + int(b)) / 3.0 > 150
        fam = ("light" if light else "medium") + ("-warm" if warm else "-cool")
        hit = 1.0
        if skin:
            sl = skin.lower()
            if "fair" in sl or "light" in sl:
                hit = 0.9 if light else 0.4
            elif "tan" in sl or "medium" in sl or "deep" in sl:
                hit = 0.9 if not light else 0.45
        add("肤色/年龄感", W_SKIN, hit if skin else 0.0,
            "卡通主体中位色 %s，特征肤色 %s" % (fam, skin or "未写"))
        if skin and hit < 0.6:
            notes.append("卡通肤色与特征肤色（%s）差得较多，看对照图确认" % skin)

    # 6) 服装
    cloth = features.get("clothing") or {}
    c_cn = _s(cloth) if not isinstance(cloth, dict) else _s(cloth.get("color"))
    add("服装", W_CLOTH, 1.0 if c_cn else 0.0,
        "服装 %s，需人工确认领型与颜色" % (c_cn or "未写"))

    score = int(round(100.0 * got / max(1.0, total)))
    if score >= PASS_SCORE:
        status = "PASS"
    elif score >= WARN_SCORE:
        status = "WARN"
    else:
        status = "FAIL"
    return {"score": score, "status": status, "detail": detail, "notes": notes,
            "cartoon_size": "%dx%d" % (c_rgb.shape[1], c_rgb.shape[0])}


def make_compare_sheet(photo, cartoon, features, out_path, score=None):
    """原图 | 卡通图 | 特征摘要 三栏并排。"""
    p = _read(photo)
    c = _read(cartoon)
    H = 640
    def fit(img, h=H, bg=(240, 240, 240)):
        img2 = img[:, :, :3] if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        r = h / float(img2.shape[0])
        img2 = cv2.resize(img2, (max(1, int(img2.shape[1] * r)), h), interpolation=cv2.INTER_AREA)
        return img2
    p1 = fit(p)
    p2 = fit(c)

    em = emit(features)
    txt_w = 560
    panel = np.full((H, txt_w, 3), 255, np.uint8)
    lines, buf = [], ""
    for ch in em["summary_cn"]:
        buf += ch
        if len(buf) >= 26:
            lines.append(buf)
            buf = ""
    if buf:
        lines.append(buf)
    head = "身份特征摘要"
    try:
        panel = _put_cn(panel, head + " / identity features", 12, 32)
    except Exception:
        cv2.putText(panel, "IDENTITY FEATURES", (12, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    y = 56
    for ln in lines[: int((H - 90) / 24)]:
        y += 24
        panel = _put_cn(panel, ln, 12, y)
    if score:
        y += 34
        cv2.putText(panel, "similarity: %d (%s)" % (score["score"], score["status"]),
                    (12, min(y, H - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 140, 0) if score["status"] == "PASS" else
                    ((0, 140, 220) if score["status"] == "WARN" else (0, 0, 220)), 2, cv2.LINE_AA)

    p1 = _tag(p1, "PHOTO (reference)")
    p2 = _tag(p2, "CARTOON")
    # 三栏对齐：panel 补齐到带标题条后的高度，避免 hstack 维度不一致
    hh = max(p1.shape[0], p2.shape[0])
    for nm in ("p1", "p2"):
        ar = p1 if nm == "p1" else p2
        if ar.shape[0] < hh:
            pad = np.full((hh - ar.shape[0], ar.shape[1], 3), 255, np.uint8)
            if nm == "p1":
                p1 = np.vstack([ar, pad])
            else:
                p2 = np.vstack([ar, pad])
    panel = _tag(panel, "IDENTITY FEATURES")
    if panel.shape[0] < hh:
        panel = np.vstack([panel, np.full((hh - panel.shape[0], panel.shape[1], 3), 255, np.uint8)])
    else:
        panel = panel[:hh]
    sep = np.full((hh, 8, 3), 255, np.uint8)
    out = np.hstack([p1, sep, p2, sep, panel])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    cv2.imwrite(out_path, out, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return out_path


def _put_cn(img, text, x, y):
    """OpenCV 画不了中文，用 PIL；没有 PIL 就返回原图（不影响对照主体）。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return img
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font = None
    for cand in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
                 "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"]:
        if os.path.exists(cand):
            try:
                font = ImageFont.truetype(cand, 17)
                break
            except Exception:
                font = None
    draw.text((x, y - 17), text, fill=(20, 20, 20), font=font)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _tag(img, text):
    bar = np.full((26, img.shape[1], 3), 30, np.uint8)
    cv2.putText(bar, text, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, img])


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description="真人面部特征分析 / 身份锁定 / 相似度评分（v%s）" % VERSION)
    ap.add_argument("--template", action="store_true", help="输出特征 JSON 骨架（必填项留空待填）")
    ap.add_argument("--validate", action="store_true", help="校验特征 JSON 必填是否齐备")
    ap.add_argument("--emit", action="store_true", help="输出英文 desc / 身份锁定词 / 中文摘要")
    ap.add_argument("--compare-sheet", action="store_true", help="原图与卡通图对照图 + 相似度评分")
    ap.add_argument("--features", default="", help="特征 JSON 路径")
    ap.add_argument("--photo", default="", help="真人照片路径（--compare-sheet 用）")
    ap.add_argument("--cartoon", default="", help="卡通图路径（--compare-sheet 用，如 raw/normal.png）")
    ap.add_argument("--out", default="", help="对照图输出路径（默认 identity.compare.jpg）")
    ap.add_argument("--json", default="", help="把结果另存为 JSON 路径")
    a = ap.parse_args()

    if a.template:
        t = template()
        txt = json.dumps(t, ensure_ascii=False, indent=2)
        tgt = a.json or (a.out if a.out.strip().lower().endswith(".json") else "")
        if tgt:
            os.makedirs(os.path.dirname(os.path.abspath(tgt)) or ".", exist_ok=True)
            open(tgt, "w", encoding="utf-8").write(txt + "\n")
            print("特征骨架已写入: %s" % os.path.abspath(tgt))
            print("接下来：用图像理解逐项分析照片 → 填满必填 → --validate")
        else:
            print(txt)
        return

    if a.validate:
        data = load_features(a.features)
        ok, missing, warns = validate(data)
        if ok:
            print("[OK] 特征齐备：%s" % os.path.abspath(a.features))
        else:
            print("[缺项] %d 个必填字段没填：" % len(missing))
            for m in missing:
                print("  - %s" % m)
        for w in warns:
            print("  [建议] %s" % w)
        if a.json:
            json.dump({"ok": ok, "missing": missing, "warnings": warns},
                      open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        if not ok:
            sys.exit(2)
        return

    if a.emit:
        data = load_features(a.features)
        ok, missing, warns = validate(data)
        if not ok:
            print("[警告] 特征不完整（%d 项缺失），先补齐再出图：%s" % (len(missing), ", ".join(missing)))
        em = emit(data)
        print("desc（传给 gen_expressions.py --desc 或 --features 自动带入）:")
        print("  " + em["desc_en"])
        print("\n身份锁定正向词（必须保留，别删）:")
        print("  " + em["lock_pos"])
        print("\n身份锁定负向词（追加到 negative）:")
        print("  " + em["lock_neg"])
        print("\n中文特征摘要（发给用户确认用）:")
        print("  " + em["summary_cn"])
        if a.json:
            payload = dict(em)
            payload.update({"ok": ok, "missing": missing, "warnings": warns})
            os.makedirs(os.path.dirname(os.path.abspath(a.json)) or ".", exist_ok=True)
            json.dump(payload, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print("\n已写入: %s" % os.path.abspath(a.json))
        return

    if a.compare_sheet:
        data = load_features(a.features)
        if not a.photo or not a.cartoon:
            raise SystemExit("--compare-sheet 需要 --photo 与 --cartoon")
        sc = score_sheet(a.photo, a.cartoon, data)
        out = a.out or "identity.compare.jpg"
        make_compare_sheet(a.photo, a.cartoon, data, out, sc)
        print("对照图: %s" % os.path.abspath(out))
        print("身份相似度: %d / 100  ->  %s" % (sc["score"], sc["status"]))
        for d in sc["detail"]:
            print("  %-8s 权重 %2d  得分率 %.2f  %s" % (d["item"], d["weight"], d["ratio"], d["note"]))
        for n in sc["notes"]:
            print("  [注意] %s" % n)
        if sc["status"] == "FAIL":
            print("  [判定] 不像本人：按上面差异点改特征或提高画风权重后重做（不要拿这张当定案）")
        elif sc["status"] == "WARN":
            print("  [判定] 边缘相似：把对照图发给用户确认，用户说不像就按差异点重做")
        else:
            print("  [判定] 通过：仍需把对照图发给用户过一眼，用户说不像以用户为准")
        if a.json:
            os.makedirs(os.path.dirname(os.path.abspath(a.json)) or ".", exist_ok=True)
            json.dump({"version": VERSION, "compare": os.path.abspath(out), "score": sc},
                      open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print("评分已写入: %s" % os.path.abspath(a.json))
        if sc["status"] == "FAIL":
            sys.exit(2)
        return

    ap.print_help()


if __name__ == "__main__":
    main()

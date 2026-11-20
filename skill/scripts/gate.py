# -*- coding: utf-8 -*-
"""
gate.py — 交互门禁（v1.1 新增，v1.2 加背景检查，v1.3 加身份一致性）

作用：把"必须问用户的三件事"从说明书里的软要求，变成落到磁盘上的硬约束。
      build_game.py 在构建前会检查 gate.json，缺项直接拒绝构建。

四道门禁：
  1. photo        照片来源已由用户明确指定（上传 / 本机路径 / 从检索候选中挑选）
  2. expressions  表情小样已给用户看过，用户已明确三选一（全部通过 / 全部重做 / 指定重做）
  3. prize        惊喜图来源已确认（用户上传 / 系统生成），文字方案已确认
  4. identity     （v1.3）卡通形象与真人特征一致：特征 JSON 齐备 + 相似度评分达标 + 对照图存在

用法：
  python {baseDir}/scripts/gate.py --file work/敲小人/gate.json --show
  python {baseDir}/scripts/gate.py --file work/敲小人/gate.json \
      --photo "D:/照片/me.jpg" --source user_upload --quote "用我上传的这张"
  python {baseDir}/scripts/gate.py --file work/敲小人/gate.json \
      --expressions all_pass --sheet work/敲小人/raw/sheet.jpg --quote "全部通过"
  python {baseDir}/scripts/gate.py --file work/敲小人/gate.json \
      --prize ai_generated --poses 3 --text "请喝咖啡" --text-source user --quote "文字用这个"
  python {baseDir}/scripts/gate.py --file work/敲小人/gate.json \
      --identity-features work/敲小人/features.json --identity-score 86 \
      --identity-compare work/敲小人/compare/identity.jpg --quote "挺像我的，继续"
  python {baseDir}/scripts/gate.py --file work/敲小人/gate.json --reset expressions

硬规则（写进 SKILL.md，违反即视为任务失败）：
  - --quote 必须逐字引用用户的原话，禁止自行编造；没有用户回复就不要写门禁。
  - photo 门禁的 --source 必须是 user_upload / user_path / user_picked 之一。
    agent 擅自检索并直接采用照片（source=agent_searched 且无用户挑选记录）不允许通过。
  - identity 门禁（v1.3）必须同时给齐特征 JSON、相似度评分、对照图，且评分 < 65 直接拒绝。
  - 门禁文件一旦写入，--quote 与时间戳留痕，便于事后追溯是哪一句用户回复授权的。
"""
import argparse
import importlib.util
import json
import os
import sys
import time

IDENTITY_FAIL_SCORE = 65          # 低于此分不放行（与 identity.py 保持一致）
IDENTITY_PASS_SCORE = 80

SOURCES_PHOTO = {
    "user_upload": "用户上传的图片",
    "user_path": "用户给出的本机路径",
    "user_picked": "从检索候选中由用户挑选",
}
SOURCES_PRIZE = {
    "user_upload": "用户上传的惊喜图",
    "ai_generated": "系统生成（基于表情人物全身卡通）",
    "compose": "本地合成（拿用户照片套奖励样式，一次出多版供挑）",
}
EXPR_DECISIONS = {
    "all_pass": "全部通过",
    "redo_all": "全部重做",
    "partial": "指定部分重做（重做完成后需再次确认）",
}

OK, WARN = "  [OK]", "  [!!]"


def _load_identity_mod():
    """复载同目录的 identity.py，复用它的字段口径与评分阈值。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "identity.py")
    if not os.path.exists(cand):
        return None
    spec = importlib.util.spec_from_file_location("pmg_identity_gate", cand)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load(p):
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save(p, d):
    os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
    d["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())


def need_quote(a, what):
    q = (a.quote or "").strip()
    if not q:
        sys.exit("  [错误] %s 门禁必须用 --quote 附上用户原话，不能凭空写入。"
                 "若用户还没回复，请先去问，不要写门禁。" % what)
    return q


def stamp(d, key, payload):
    d[key] = payload
    d[key]["_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return d


def summarize(d):
    print("\n门禁状态  %s" % (d.get("file") or "gate.json"))
    ph, ex, pz = d.get("photo") or {}, d.get("expressions") or {}, d.get("prize") or {}
    if ph.get("confirmed"):
        print(OK + " 1.照片  %s → %s  (用户说：%s)" % (
            SOURCES_PHOTO.get(ph.get("source"), ph.get("source")), ph.get("path"), ph.get("quote")))
    else:
        print(WARN + " 1.照片  未确认 —— 必须先问用户照片从哪来")
    if ex.get("confirmed"):
        print(OK + " 2.表情  %s  (用户说：%s)" % (
            EXPR_DECISIONS.get(ex.get("decision"), ex.get("decision")), ex.get("quote")))
    else:
        print(WARN + " 2.表情  未确认 —— 必须先把小样给用户看并等三选一回复")
    if pz.get("confirmed"):
        scope_cn = {"same": "全难度共用一张", "per_diff": "每个难度各一张"}.get(pz.get("scope"), "覆盖范围未确认")
        print(OK + " 3.惊喜  %s / %s  文字=%s  (用户说：%s)" % (
            SOURCES_PRIZE.get(pz.get("source"), pz.get("source")), scope_cn,
            ("「%s」/来源 %s" % (pz.get("text"), pz.get("text_source"))) if pz.get("text") else "无文字",
            pz.get("quote")))
        if pz.get("scope") == "per_diff":
            for k, v in (pz.get("map") or {}).items():
                print("          %-7s -> %s" % (k, v))
        elif pz.get("pick"):
            print("          通用图 -> %s" % pz.get("pick"))
    else:
        print(WARN + " 3.惊喜  未确认 —— 必须问齐三件事：①上传还是系统生成 "
                     "②同一张还是每个难度各一张 ③图上文字谁给")
    idf = d.get("identity") or {}
    if idf.get("confirmed"):
        print(OK + " 4.身份  相似度 %s 分（%s）/ 对照图 %s  (用户说：%s)" % (
            idf.get("score"), idf.get("status"), idf.get("compare"), idf.get("quote")))
    else:
        print(WARN + " 4.身份  未确认 —— 必须先做真人特征分析 + 原图与卡通对照评分，"
                     "并拿到用户「像不像」的明确回复")
    left = [k for k, v in (("photo", ph), ("expressions", ex), ("prize", pz),
                           ("identity", idf)) if not v.get("confirmed")]
    print("\n缺口: %s" % ("、".join(left) if left else "无，可以构建游戏"))
    return left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="gate.json", help="门禁文件路径，建议 work/<主题>/gate.json")
    ap.add_argument("--show", action="store_true", help="只看当前状态")
    ap.add_argument("--reset", default="",
                    help="重置某道门禁：photo / expressions / prize / identity / all")

    g = ap.add_argument_group("门禁 4 身份一致性（v1.3）")
    g.add_argument("--identity-features", default="",
                   help="真人面部特征 JSON（identity.py --template 产出），必须通过 --validate")
    g.add_argument("--identity-score", type=int, default=-1,
                   help="原图与卡通图的相似度评分（0~100，identity.py --compare-sheet 给出）")
    g.add_argument("--identity-compare", default="",
                   help="原图与卡通的对照图路径（identity.py --compare-sheet 产出）")

    g = ap.add_argument_group("门禁 1 照片")
    g.add_argument("--photo", default="", help="用户选定的照片绝对路径")
    g.add_argument("--source", default="user_upload", choices=list(SOURCES_PHOTO.keys()))
    g.add_argument("--candidates", default="", help="user_picked 时记录候选清单，逗号分隔")

    g = ap.add_argument_group("门禁 2 表情小样")
    g.add_argument("--expressions", default="", choices=list(EXPR_DECISIONS.keys()))
    g.add_argument("--sheet", default="", help="发给用户看的拼图路径")
    g.add_argument("--redo", default="", help="decision=partial 时列出要重做的 key")

    g = ap.add_argument_group("门禁 3 惊喜图")
    g.add_argument("--prize", default="", choices=list(SOURCES_PRIZE.keys()))
    g.add_argument("--poses", type=int, default=3, help="系统生成时的姿势数")
    g.add_argument("--text", default="", help="惊喜图上的文字，空=不带字")
    g.add_argument("--text-source", default="agent", choices=["user", "agent"], help="文字谁给的")
    g.add_argument("--pick", default="", help="多姿势中用户选定的那张（scope=same 时即通用图）")
    g.add_argument("--scope", default="", choices=["", "same", "per_diff"],
                   help="惊喜图覆盖范围：same=所有难度共用一张；per_diff=每个通关难度各一张")
    g.add_argument("--prize-map", default="",
                   help="scope=per_diff 时逐难度映射，格式 normal:a.jpg;hard:b.jpg;hell:c.jpg")
    g.add_argument("--diffs", default="normal,hard,hell",
                   help="需要惊喜图的难度（默认排除 easy 轻松难度）")

    ap.add_argument("--quote", default="", help="用户原话（必填，禁止编造）")
    a = ap.parse_args()

    d = load(a.file)
    d["file"] = os.path.abspath(a.file)
    d.setdefault("version", "1.3")

    if a.reset:
        for k in (["photo", "expressions", "prize", "identity"] if a.reset == "all" else [a.reset]):
            d.pop(k, None)
        save(a.file, d)
        print("  已重置: %s" % a.reset)
        return summarize(d)

    changed = False

    if a.photo:
        p = os.path.abspath(os.path.expanduser(a.photo))
        if not os.path.exists(p):
            sys.exit("  [错误] 照片不存在: %s —— 请先确认用户给的文件真的在磁盘上" % p)
        if a.source == "user_picked" and not a.candidates.strip():
            sys.exit("  [错误] source=user_picked 需要用 --candidates 记录给用户挑过的候选，"
                     "否则无法证明是用户挑的")
        q = need_quote(a, "照片")
        stamp(d, "photo", {"confirmed": True, "path": p, "source": a.source,
                           "candidates": [x.strip() for x in a.candidates.split(",") if x.strip()],
                           "quote": q})
        changed = True

    if a.expressions:
        if not a.sheet:
            sys.exit("  [错误] 表情门禁需要 --sheet 指向已发给用户的拼图（先用 make_sheet.py 生成）")
        sp = os.path.abspath(os.path.expanduser(a.sheet))
        if not os.path.exists(sp):
            sys.exit("  [错误] 拼图不存在: %s —— 没给小样就不能算确认过" % sp)
        if a.expressions == "partial" and not a.redo.strip():
            sys.exit("  [错误] decision=partial 需要用 --redo 列出要重做的 key")
        # v1.2：小样背景必须是利于后期抠图的纯色，make_sheet.py 的 bgcheck 有 FAIL 就不许确认
        bgf = os.path.splitext(sp)[0] + ".bgcheck.json"
        if os.path.exists(bgf):
            try:
                bj = json.load(open(bgf, encoding="utf-8"))
            except Exception:
                bj = {}
            fails = bj.get("fail") or []
            if fails and a.expressions != "redo_all":
                sys.exit("  [错误] 这些小样背景不合格（渐变/场景/无背景可依），抠图必花边，"
                         "必须先按纯色重生再确认：\n           %s\n"
                         "           重生示例：gen_expressions.py --only <key> --bg magenta\n"
                         "           检查报告：%s" % ("、".join(fails), bgf))
            if bj.get("warn"):
                print("  [提示] %d 张小样背景是自定义纯色（非预设），能抠但建议换 magenta/green" % bj["warn"])
        else:
            print("  [提示] 未找到 %s，跳过小样背景校验（建议用 make_sheet.py 默认的 --check-bg 生成）"
                  % os.path.basename(bgf))
        q = need_quote(a, "表情")
        stamp(d, "expressions", {"confirmed": True, "decision": a.expressions, "sheet": sp,
                                 "redo": [x.strip() for x in a.redo.split(",") if x.strip()],
                                 "quote": q})
        changed = True

    if a.prize:
        diffs = [x.strip() for x in a.diffs.split(",") if x.strip()]
        if not a.scope:
            sys.exit("  [错误] v1.2 起惊喜图必须确认覆盖范围，用 --scope 二选一：\n"
                     "           same      = 除轻松外所有难度通关后都用同一张\n"
                     "           per_diff  = 每个通关难度各一张不同图\n"
                     "         这一项没有默认值 —— 必须真的问过用户再写门禁。")
        pmap = {}
        for seg in a.prize_map.split(";"):
            if ":" in seg:
                k, v = seg.split(":", 1)
                if k.strip() and v.strip():
                    pmap[k.strip()] = os.path.abspath(os.path.expanduser(v.strip()))
        if a.scope == "same":
            if not a.pick:
                sys.exit("  [错误] scope=same 需要用 --pick 指定那张通用惊喜图"
                         "（用户上传的图，或系统生成后用户选定的那张）")
            if not os.path.exists(os.path.abspath(os.path.expanduser(a.pick))):
                sys.exit("  [错误] 惊喜图不存在: %s" % a.pick)
            if a.prize == "ai_generated" and a.poses > 1 and not a.pick:
                sys.exit("  [错误] 系统生成 %d 个姿势后必须让用户挑一张" % a.poses)
        else:  # per_diff
            if not pmap:
                sys.exit("  [错误] scope=per_diff 需要用 --prize-map 逐难度交定案图，"
                         "格式正常:a.jpg;困难:b.jpg;地狱:c.jpg（用英文 key：normal/hard/hell）")
            miss = [k for k in diffs if k not in pmap]
            if miss:
                sys.exit("  [错误] 这些难度还没有定案惊喜图: %s\n"
                         "          除轻松(easy)外每个通关难度都必须有惊喜图，缺一张都不行。"
                         % "、".join(miss))
            bad = [k for k in pmap if not os.path.exists(pmap[k])]
            if bad:
                sys.exit("  [错误] 这些难度指定的图不存在: %s"
                         % "、".join("%s=%s" % (k, pmap[k]) for k in bad))
        q = need_quote(a, "惊喜图")
        stamp(d, "prize", {"confirmed": True, "source": a.prize, "poses": a.poses,
                           "scope": a.scope, "diffs": diffs, "map": pmap,
                           "text": a.text.strip(), "text_source": a.text_source if a.text.strip() else "",
                           "pick": os.path.abspath(os.path.expanduser(a.pick)) if a.pick else "",
                           "quote": q})
        changed = True

    id_requested = bool(a.identity_features.strip() or a.identity_compare.strip()
                        or a.identity_score >= 0)
    if id_requested:
        if not a.identity_features.strip():
            sys.exit("  [错误] 身份门禁必须先用 --identity-features 指定真人特征 JSON"
                     "（identity.py --template 产出，逐字段填好后过 --validate）")
        fp = os.path.abspath(os.path.expanduser(a.identity_features.strip()))
        if not os.path.exists(fp):
            sys.exit("  [错误] 特征 JSON 不存在: %s —— 没做过特征分析就不算确认过身份" % fp)
        mod = _load_identity_mod()
        if mod is None:
            sys.exit("  [错误] 缺少 scripts/identity.py，无法校验特征 JSON")
        data = mod.load_features(fp)
        ok, missing, warns = mod.validate(data)
        if not ok:
            sys.exit("  [错误] 特征 JSON 还有 %d 项必填为空：%s\n"
                     "           先把这些字段补上（问用户或看图确认），再做对照评分。"
                     % (len(missing), "、".join(missing)))
        if a.identity_score < 0:
            sys.exit("  [错误] 身份门禁必须用 --identity-score 给出相似度评分（0~100），"
                     "由 identity.py --compare-sheet 产出")
        if a.identity_score > 100:
            sys.exit("  [错误] --identity-score 范围 0~100，收到 %d" % a.identity_score)
        if a.identity_score < IDENTITY_FAIL_SCORE:
            sys.exit("  [错误] 相似度 %d 分低于放行线 %d —— 这版卡通不像本人，不许当定案。\n"
                     "           请先按差异点重做（改 features 里不符的字段 → gen_expressions.py "
                     "--features 重出 → 重新对照评分），不要在这里硬调。"
                     % (a.identity_score, IDENTITY_FAIL_SCORE))
        if not a.identity_compare.strip():
            sys.exit("  [错误] 身份门禁必须用 --identity-compare 指定原图与卡通的对照图"
                     "（identity.py --compare-sheet 产出），没有对照图不认")
        cp = os.path.abspath(os.path.expanduser(a.identity_compare.strip()))
        if not os.path.exists(cp):
            sys.exit("  [错误] 对照图不存在: %s —— 必须真的生成过对照图" % cp)
        q = need_quote(a, "身份一致性")
        status = "PASS" if a.identity_score >= IDENTITY_PASS_SCORE else "WARN"
        if status == "WARN":
            print("  [提示] 相似度 %d 分属于「勉强能认」（PASS 线 %d）：建议先问用户像不像，"
                  "不要自己判断'差不多'" % (a.identity_score, IDENTITY_PASS_SCORE))
        print("  身份锁定词: %s" % (mod.emit(data).get("lock_pos") or ""))
        stamp(d, "identity", {"confirmed": True, "score": a.identity_score, "status": status,
                              "features": fp, "compare": cp,
                              "summary_cn": mod.emit(data).get("summary_cn", ""),
                              "warnings": warns, "quote": q})
        changed = True

    if changed:
        save(a.file, d)
        print("  已写入 %s" % os.path.abspath(a.file))
    return summarize(d)


if __name__ == "__main__":
    main()

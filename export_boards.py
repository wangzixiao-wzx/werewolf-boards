#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 werewolf.db 导出「狼人杀版型库」静态数据。

只读取 board / board_role / board_rule / role / faction 五张配置表，
绝不读取 game / game_player / player / player_alias 等对局与玩家表，
因此产物不含任何玩家昵称、战绩或行为数据，可安全公开发布。

用法：
    python export_boards.py                # 生成 boards.json / data.js / BOARDS.md
    python export_boards.py --db 其它.db   # 指定数据库
    python export_boards.py --check        # 只校验，不写文件
"""
import argparse
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT.parent / "werewolf-stats" / "werewolf.db"

# 导入时批量写入的占位备注，没有信息量，不展示
NOISE = {
    "由文档导入自动生成", "由文档导入", "自动生成", "由文档导入生成",
    "由文档导入生成，待补充", "-", "无", "",
}
# 录入来源 / 内部实现痕迹：既不是版型规则，也可能带日期或数据库字段名，公开版一律剔除
INTERNAL = re.compile(
    r"由文档导入|批量导入|导入补录|由源文档整理|用户提供定义|"
    r"由用户提供的板子定义建板|尚无对局|库里无|board_role|role_id|"
    r"game\.note|记录约定|录入约定|数据库约定|20\d\d-\d\d-\d\d"
)


def clean(v):
    v = str(v or "").strip()
    if v in NOISE:
        return ""
    # 备注尾部若带内部录入约定，只截掉这一段，保留前面的规则说明
    v = re.split(r"记录约定[:：]|录入约定[:：]|数据库约定[:：]", v)[0]
    # 「[批量导入]」这类标记单独去掉，前面的板子说明仍有价值
    v = re.sub(r"\[?批量导入\]?", "", v)
    if INTERNAL.search(v):
        return ""
    # 本地源文件名、录入状态等痕迹也去掉，但保留其余规则描述
    v = re.sub(r"来源[:：]\s*[\w\-.]+\.txt\s*[；;，,]?\s*", "", v)
    v = re.sub(r"规则详见文档|对局暂未录入", "", v)
    v = re.sub(r"[；;，,]{2,}", "，", v)
    v = re.sub(r"[（(]\s*[）)]", "", v)
    v = v.strip(" ；;，,（）()")
    if v.count("（") > v.count("）"):
        v += "）"
    if v.count("(") > v.count(")"):
        v += ")"
    return "" if v in NOISE else v


def build(db_path):
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    factions = [
        {"id": r["id"], "name": r["name"], "color": r["color"]}
        for r in con.execute("SELECT id,name,color FROM faction ORDER BY sort_no,id")
    ]
    fmap = {f["id"]: f["name"] for f in factions}

    roles = {}
    for r in con.execute(
        "SELECT id,name,faction_id,note FROM role ORDER BY sort_no,id"
    ):
        roles[r["id"]] = {
            "id": r["id"],
            "name": r["name"],
            "faction_id": r["faction_id"],
            "faction": fmap.get(r["faction_id"], "未知阵营"),
            "note": clean(r["note"]),
            "boards": [],
        }

    boards = []
    for b in con.execute(
        "SELECT id,name,player_count,judge_count,note FROM board ORDER BY id"
    ):
        cards = []
        for br in con.execute(
            "SELECT role_id,cnt FROM board_role WHERE board_id=? ORDER BY id", (b["id"],)
        ):
            ro = roles.get(br["role_id"])
            if not ro:
                continue
            cards.append({
                "role_id": ro["id"],
                "role": ro["name"],
                "faction_id": ro["faction_id"],
                "faction": ro["faction"],
                "count": br["cnt"],
            })
            if b["id"] not in ro["boards"]:
                ro["boards"].append(b["id"])

        rules = []
        for rr in con.execute(
            "SELECT role_id,rule_key,rule_value,note FROM board_rule "
            "WHERE board_id=? ORDER BY id", (b["id"],)
        ):
            value = clean(rr["rule_value"])
            if not value:
                continue
            # rule.note 全部是录入来源备注（由源文档整理 / 导入补录 / 内部字段名），
            # 没有公开价值，直接不导出，避免把实现细节带进公开仓库。
            rules.append({
                "key": clean(rr["rule_key"]) or "规则",
                "value": value,
                "role": roles[rr["role_id"]]["name"] if rr["role_id"] in roles else "",
            })

        note = clean(b["note"])
        card_count = sum(c["count"] for c in cards)
        seats = b["player_count"]
        haystack = " ".join([
            b["name"], str(seats) + "人", note,
            " ".join(c["role"] for c in cards),
            " ".join(r["key"] + " " + r["value"] + " " + r["role"] for r in rules),
        ]).lower()

        boards.append({
            "id": b["id"],
            "name": b["name"],
            "seats": seats,
            "judge": b["judge_count"] or 0,
            "note": note,
            "cards": cards,
            "card_count": card_count,
            "multi_card": card_count != seats,   # 盗贼/丘比特/双身份等：牌数 ≠ 座位数
            "rules": rules,
            "search": haystack,
        })

    roles_out = [
        {k: v for k, v in ro.items() if k != "boards"} | {"board_count": len(ro["boards"]), "boards": ro["boards"]}
        for ro in sorted(roles.values(), key=lambda x: (x["faction_id"], x["id"]))
    ]

    data = {
        "meta": {
            "title": "狼人杀版型库",
            "generated": date.today().isoformat(),
            "board_count": len(boards),
            "role_count": len(roles_out),
            "rule_count": sum(len(b["rules"]) for b in boards),
            "faction_count": len(factions),
            "disclaimer": "仅收录板型配置（板子 / 身份 / 特殊规则），不含任何对局记录、玩家昵称或统计数据。",
            "source": "本地 werewolf.db 配置表，由 export_boards.py 自动生成",
        },
        "factions": factions,
        "roles": roles_out,
        "boards": boards,
    }
    con.close()
    return data


def markdown(data):
    m = data["meta"]
    out = [
        "# 版型清单",
        "",
        f"> 由 `export_boards.py` 自动生成，请勿手改。共 **{m['board_count']}** 个版型、"
        f"**{m['role_count']}** 个身份、**{m['rule_count']}** 条特殊规则。",
        f"> {m['disclaimer']}",
        "",
        "## 目录",
        "",
    ]
    for b in data["boards"]:
        out.append(f"- [{b['name']}](#board-{b['id']}) · {b['seats']} 人")
    out.append("")
    for b in data["boards"]:
        out += [f"<a id=\"board-{b['id']}\"></a>", "", f"## {b['name']}", ""]
        bits = [f"**{b['seats']} 人局**"]
        if b["judge"]:
            bits.append(f"法官 {b['judge']} 人")
        bits.append(f"身份牌 {b['card_count']} 张")
        if b["multi_card"]:
            bits.append("⚠️ 牌数 ≠ 座位数（含额外身份牌 / 双身份）")
        if b["note"]:
            bits.append(b["note"])
        out += [" · ".join(bits), "", "| 阵营 | 身份 | 张数 |", "| --- | --- | ---: |"]
        for c in b["cards"]:
            out.append(f"| {c['faction']} | {c['role']} | {c['count']} |")
        if b["rules"]:
            out += ["", "**特殊规则**", ""]
            for i, r in enumerate(b["rules"], 1):
                prefix = f"[{r['key']}] " if r["key"] else ""
                who = f"（{r['role']}）" if r["role"] else ""
                out.append(f"{i}. {prefix}{who}{r['value']}")
        out.append("")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description="导出版型库静态数据")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="werewolf.db 路径")
    ap.add_argument("--out", default=str(ROOT), help="输出目录")
    ap.add_argument("--check", action="store_true", help="只校验不写文件")
    a = ap.parse_args()

    db = Path(a.db)
    if not db.exists():
        raise SystemExit(f"数据库不存在：{db}")
    data = build(db)
    m = data["meta"]

    # 一致性校验
    errs = []
    for b in data["boards"]:
        if not b["cards"]:
            errs.append(f"板子 {b['id']} {b['name']} 没有身份配置")
        if sum(c["count"] for c in b["cards"]) != b["card_count"]:
            errs.append(f"板子 {b['id']} 张数不一致")
    if len({b["id"] for b in data["boards"]}) != m["board_count"]:
        errs.append("板子 id 重复")
    if errs:
        raise SystemExit("校验失败：\n" + "\n".join(errs))

    print(f"校验通过：{m['board_count']} 板型 / {m['role_count']} 身份 / "
          f"{m['rule_count']} 规则 / 生成于 {m['generated']}")
    multi = [b["name"] for b in data["boards"] if b["multi_card"]]
    print(f"牌数≠座位数：{len(multi)} 个 → {', '.join(multi)}")

    if a.check:
        print("--check：未写文件")
        return
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "boards.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "data.js").write_text(
        "/* 自动生成，请勿手改；运行 python export_boards.py 重新生成 */\n"
        "window.BOARD_DATA = " +
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")
    (out / "BOARDS.md").write_text(markdown(data), encoding="utf-8")
    for f in ("boards.json", "data.js", "BOARDS.md"):
        print(f"  {f}  {(out / f).stat().st_size:,} 字节")


if __name__ == "__main__":
    main()

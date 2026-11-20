"""跨学期写作辅导安排：目标认定、练习推荐、有条件选课。

规则要点（与 README 的资料约定对应）：
- 同一 occasion 的不同形式只算一次隔次观察，同一次观察不能充当两次隔次进展。
- 小组记录只作背景，除非确认记录中有本人追认。
- 辅助完成的观察可用于教学，不能结清要求独立说明的目标。
- 确认记录按 day 更新，以最新状态为准；reject 否定上次确认，
  contested 表示意见仍相冲，二者都不算通过。
- 先修可由资料承认的任一路径满足，缺一条路径不拦住已走通另一条的人。
- 证据有效期按目标 valid_terms 解释；超期记录可回查但不计入。
- 练习推荐要求：学生可到、容量足够、练习独立性满足目标要求、
  预计确认日（含教师变更）不晚于下一门课开课日。
- 已约练习给本人保留；确认记录变更使其不再适用时提示负责老师改约，
  不悄悄换人。
- 有条件选课：目标未达但存在完整路径（已约或可约练习、确认日不晚于
  改选截止）才可给条件名额；每人只承诺一个正式班次；候补不占正式班
  容量；证据争议未决不得以估计达标先入课；预测的练习结果不计入已学会。
"""

from collections import defaultdict
from pathlib import Path
import sys

from record_reader import read_records

ROOT = Path(__file__).resolve().parent / "records"

GAP_LABELS = {
    "no_record": "纯缺记录",
    "missing_occasion": "隔次不足",
    "assisted_only": "仅辅助记录",
    "contradicted": "记录被否定或相冲",
    "expired": "证据超期",
    "prereq_missing": "先修未满",
}


# ---------- 基础派生 ----------

def current_term(tables):
    """当期学期：以注册数据给出的学期为准。"""
    return max(row["term"] for row in tables["admissions"])


def latest_rulings(tables):
    """每个 (观察, 学生) 的最新确认状态。"""
    latest = {}
    for row in tables["rulings"]:
        key = (row["observation"], row["student"])
        if key not in latest or row["day"] > latest[key]["day"]:
            latest[key] = row
    return latest


def ruling_chain(tables, observation, student):
    """某观察对某学生的全部确认记录，按日排序（用于回查争议链）。"""
    rows = [r for r in tables["rulings"]
            if r["observation"] == observation and r["student"] == student]
    return sorted(rows, key=lambda r: r["day"])


def effective_verified(tables):
    """练习预计确认日：以负责教师变更后的日期为准。"""
    verified = {w["session"]: w["verified"] for w in tables["workshops"]}
    for adj in tables["adjustments"]:
        verified[adj["session"]] = adj["revised_verified"]
    return verified


def activity_map(tables):
    """activity -> 资料认可的目标对应行列表。"""
    by_activity = defaultdict(list)
    for row in tables["observation_map"]:
        by_activity[row["activity"]].append(row)
    return by_activity


def evidence_for(tables, student, term):
    """按目标归集该生观察：认可 / 辅助 / 被否定或相冲 / 超期 / 未确认。

    小组记录（student 为空）只在确认记录中有本人追认时才归到个人；
    辅助完成的观察不能结清要求独立说明的目标；超期记录只回查不计入。
    """
    goals = {g["goal"]: g for g in tables["goals"]}
    by_activity = activity_map(tables)
    rulings = latest_rulings(tables)
    ev = {g: {"accepted": [], "assisted": [], "disputed": [],
              "expired": [], "unconfirmed": []} for g in goals}
    for obs in tables["observations"]:
        for m in by_activity.get(obs["activity"], []):
            if m["term"] != obs["term"]:
                continue
            goal = m["goal"]
            ruling = rulings.get((obs["observation"], student))
            if obs["student"] != student and ruling is None:
                continue  # 小组说明只作背景
            entry = {"obs": obs, "ruling": ruling}
            if ruling is None:
                ev[goal]["unconfirmed"].append(entry)
            elif ruling["state"] != "accept":
                ev[goal]["disputed"].append(entry)
            elif obs["support"] and goals[goal]["independent"]:
                ev[goal]["assisted"].append(entry)
            elif obs["term"] + goals[goal]["valid_terms"] <= term:
                ev[goal]["expired"].append(entry)
            else:
                ev[goal]["accepted"].append(entry)
    return ev


def goal_status(tables, student, term, extra=None):
    """每目标认定状态。extra: {goal: 额外场合集合}，用于模拟计划后的状态。"""
    goals = {g["goal"]: g for g in tables["goals"]}
    ev = evidence_for(tables, student, term)
    paths = defaultdict(dict)
    for row in tables["prerequisites"]:
        paths[row["goal"]].setdefault(row["path"], []).append(row["required"])
    extra = extra or {}
    status = {}

    def resolve(goal):
        if goal in status:
            return status[goal]
        g = goals[goal]
        occasions = {e["obs"]["occasion"] for e in ev[goal]["accepted"]}
        occasions |= set(extra.get(goal, ()))
        own_ok = len(occasions) >= g["occasions"]
        path_detail = {}
        prereq_ok = True
        if paths.get(goal):
            prereq_ok = False
            for path, reqs in sorted(paths[goal].items()):
                missing = [r for r in reqs if not resolve(r)["met"]]
                path_detail[path] = {"required": list(reqs), "missing": missing}
                if not missing:
                    prereq_ok = True
        st = {
            "goal": goal,
            "met": own_ok and prereq_ok,
            "own_ok": own_ok,
            "prereq_ok": prereq_ok,
            "occasions_have": len(occasions),
            "occasions_need": g["occasions"],
            "paths": path_detail,
            "accepted": ev[goal]["accepted"],
            "assisted": ev[goal]["assisted"],
            "disputed": ev[goal]["disputed"],
            "expired": ev[goal]["expired"],
            "unconfirmed": ev[goal]["unconfirmed"],
        }
        status[goal] = st
        return st

    for goal in goals:
        resolve(goal)
    return status


def gap_cause(st):
    """缺口主因：决定核实路径（纯缺记录补观察；证据相冲先裁定）。"""
    if st["met"]:
        return None
    if not st["prereq_ok"]:
        return "prereq_missing"
    if st["occasions_have"] > 0:
        return "missing_occasion"
    if st["disputed"]:
        return "contradicted"
    if st["assisted"]:
        return "assisted_only"
    if st["expired"]:
        return "expired"
    return "no_record"


def prereq_closure(tables, roots):
    """目标及其全部传递先修，按先修在前的顺序返回。"""
    paths = defaultdict(set)
    for row in tables["prerequisites"]:
        paths[row["goal"]].add(row["required"])
    seen, order = set(), []

    def visit(goal):
        if goal in seen:
            return
        seen.add(goal)
        for req in sorted(paths.get(goal, ())):
            visit(req)
        order.append(goal)

    for goal in sorted(roots):
        visit(goal)
    return order


# ---------- 练习推荐 ----------

def plan_student(tables, student, term, seats_left, verified):
    """为一名学生安排练习：先修在前，已约保留，容量与确认日受控。"""
    admission = next(a for a in tables["admissions"] if a["student"] == student)
    workshops = {w["session"]: w for w in tables["workshops"]}
    goals = {g["goal"]: g for g in tables["goals"]}
    sections = {s["section"]: s for s in tables["sections"]}
    prefs = next((r["preference"] for r in tables["preferences"]
                  if r["student"] == student), [])
    avail = {r["day"] for r in tables["availability"] if r["student"] == student}
    booked = {a["session"] for a in tables["appointments"]
              if a["student"] == student}
    status = goal_status(tables, student, term)
    roots = {admission["required"]}
    roots |= {sections[p]["requirement"] for p in prefs if p in sections}
    relevant = prereq_closure(tables, roots)
    extra = defaultdict(set)
    steps = []
    shortfalls = []
    for goal in relevant:
        need = goals[goal]["occasions"] - status[goal]["occasions_have"]
        while need - len(extra[goal]) > 0:
            chosen = None
            rejected = []
            ordered = sorted(
                workshops,
                key=lambda s: (0 if s in booked else 1,
                               verified[s], workshops[s]["day"], s))
            for s in ordered:
                w = workshops[s]
                if goal not in w["covers"]:
                    continue
                why = []
                if goals[goal]["independent"] and not w["independent"]:
                    why.append("练习非独立，不能结清独立目标")
                if verified[s] > admission["start_day"]:
                    why.append(f"确认日{verified[s]}晚于开课日{admission['start_day']}")
                if s not in booked:
                    if w["day"] not in avail:
                        why.append(f"第{w['day']}日不可到")
                    elif seats_left[s] <= 0:
                        why.append("容量已满")
                if why:
                    rejected.append({"session": s, "why": why})
                    continue
                chosen = s
                break
            if chosen is None:
                shortfalls.append({"goal": goal,
                                   "lacking": need - len(extra[goal]),
                                   "rejected": rejected})
                break
            w = workshops[chosen]
            if chosen not in booked:
                seats_left[chosen] -= 1
            addressed = []
            for g2 in relevant:
                if g2 not in w["covers"]:
                    continue
                if goals[g2]["occasions"] - status[g2]["occasions_have"] - len(extra[g2]) > 0:
                    extra[g2].add(chosen)
                    addressed.append(g2)
            steps.append({
                "session": chosen,
                "day": w["day"],
                "verified": verified[chosen],
                "goals": sorted(addressed),
                "kept_booking": chosen in booked,
            })
    after = goal_status(tables, student, term,
                        extra={g: set(v) for g, v in extra.items()})
    return {
        "student": student,
        "admission": admission,
        "preference": prefs,
        "relevant": relevant,
        "status": status,
        "after": after,
        "steps": steps,
        "shortfalls": shortfalls,
    }


def appointment_audit(tables, plan):
    """已约练习仍适用则保留；不再适用时提示负责老师改约，不悄悄换人。"""
    workshops = {w["session"]: w for w in tables["workshops"]}
    out = []
    for a in tables["appointments"]:
        if a["student"] != plan["student"]:
            continue
        w = workshops[a["session"]]
        needed = [g for g in w["covers"] if not plan["status"][g]["met"]]
        out.append({
            "session": a["session"],
            "applicable": bool(needed),
            "covers_needed": needed,
        })
    return out


# ---------- 有条件选课 ----------

def enrollment_student(tables, plan, term, tally):
    """评估一名学生的志愿班次与既有回执，给出唯一正式承诺。"""
    sections = {s["section"]: s for s in tables["sections"]}
    offers = {}
    for p in plan["preference"]:
        if p not in sections:
            continue
        sec = sections[p]
        req = sec["requirement"]
        if plan["status"][req]["met"]:
            offers[p] = {"kind": "official", "req": req}
            continue
        closure = prereq_closure(tables, {req})
        used = [st for st in plan["steps"] if set(st["goals"]) & set(closure)]
        if plan["after"][req]["met"]:
            late = [st for st in used if st["verified"] > sec["switch_until"]]
            if late:
                offers[p] = {"kind": "none", "req": req, "reason": "late",
                             "deadline": sec["switch_until"],
                             "latest": max(st["verified"] for st in used)}
            else:
                offers[p] = {"kind": "conditional", "req": req, "steps": used}
            continue
        blockers = []
        for g in closure:
            if plan["after"][g]["met"]:
                continue
            sf = next((x for x in plan["shortfalls"] if x["goal"] == g), None)
            contested = [e for e in plan["status"][g]["disputed"]
                         if e["ruling"] and e["ruling"]["state"] == "contested"]
            blockers.append({"goal": g, "shortfall": sf,
                             "contested": bool(contested)})
        offers[p] = {"kind": "none", "req": req, "reason": "unreachable",
                     "blockers": blockers}
    existing = []
    commitment = None
    for row in tables["seats"]:
        if row["student"] != plan["student"]:
            continue
        sec = sections[row["section"]]
        req = sec["requirement"]
        if row["state"] == "conditional":
            closure = prereq_closure(tables, {req})
            used = [st for st in plan["steps"] if set(st["goals"]) & set(closure)]
            ok = (plan["after"][req]["met"]
                  and all(st["verified"] <= sec["switch_until"] for st in used))
            if ok:
                existing.append({**row, "verdict": "维持"})
                commitment = commitment or row["section"]
                tally[row["section"]]["conditional"].append(plan["student"])
            else:
                existing.append({**row, "verdict": "作废"})
                tally[row["section"]]["voided"].append(plan["student"])
        elif row["state"] == "waiting":
            existing.append({**row, "verdict": "保留候补",
                             "reachable": plan["after"][req]["met"]})
            tally[row["section"]]["waiting"].append(plan["student"])
    if commitment is None:
        for p in plan["preference"]:
            offer = offers.get(p)
            if offer and offer["kind"] in ("official", "conditional"):
                commitment = p
                tally[p]["conditional"].append(plan["student"])
                break
    return {"offers": offers, "existing": existing, "commitment": commitment}


# ---------- 班组分布与回查 ----------

def cohort_distribution(tables, plans):
    """按目标分桶：已达标 / 待核实(已有完整计划) / 部分证据 / 无法按期。

    预测的练习结果只进“待核实”，不计入“已达标”。
    """
    out = {g["goal"]: {"met": [], "planned": [], "partial": [], "blocked": []}
           for g in tables["goals"]}
    for stu, plan in plans.items():
        for g in plan["relevant"]:
            st = plan["status"][g]
            if st["met"]:
                out[g]["met"].append(stu)
            elif plan["after"][g]["met"]:
                out[g]["planned"].append(stu)
            elif st["occasions_have"] > 0 or st["own_ok"]:
                out[g]["partial"].append(stu)
            else:
                out[g]["blocked"].append(stu)
    return out


def comparisons(tables, plans, verified):
    """同款建议为何不适用于记录表面相似的同学。"""
    workshops = {w["session"]: w for w in tables["workshops"]}
    goals = {g["goal"]: g for g in tables["goals"]}
    out = defaultdict(list)
    for stu, plan in plans.items():
        for step in plan["steps"]:
            for goal in step["goals"]:
                for other, oplan in plans.items():
                    if other == stu or oplan["status"][goal]["met"]:
                        continue
                    booked = {a["session"] for a in tables["appointments"]
                              if a["student"] == other}
                    if step["session"] in booked:
                        continue  # 对本人同样适用：已约保留
                    w = workshops[step["session"]]
                    reasons = []
                    if goals[goal]["independent"] and not w["independent"]:
                        reasons.append("练习非独立，不能结清独立目标")
                    if verified[step["session"]] > oplan["admission"]["start_day"]:
                        reasons.append(
                            f"确认日{verified[step['session']]}晚于开课日"
                            f"{oplan['admission']['start_day']}")
                    avail = {r["day"] for r in tables["availability"]
                             if r["student"] == other}
                    if w["day"] not in avail:
                        reasons.append(f"第{w['day']}日不可到")
                    if reasons:
                        out[(stu, step["session"], goal)].append((other, reasons))
    return out


# ---------- 汇总入口 ----------

def analyze(folder=ROOT):
    tables = read_records(folder)
    term = current_term(tables)
    verified = effective_verified(tables)
    students = sorted({a["student"] for a in tables["admissions"]})
    seats_left = {w["session"]: w["seats"] for w in tables["workshops"]}
    for a in tables["appointments"]:
        seats_left[a["session"]] -= 1
    plans = {}
    for stu in students:
        plans[stu] = plan_student(tables, stu, term, seats_left, verified)
    tally = {s["section"]: {"conditional": [], "official": [],
                            "waiting": [], "voided": []}
             for s in tables["sections"]}
    enroll = {}
    for stu in students:
        enroll[stu] = enrollment_student(tables, plans[stu], term, tally)
    return {
        "tables": tables,
        "term": term,
        "verified": verified,
        "seats_left": seats_left,
        "plans": plans,
        "enroll": enroll,
        "tally": tally,
        "distribution": cohort_distribution(tables, plans),
        "comparisons": comparisons(tables, plans, verified),
        "audits": {stu: appointment_audit(tables, plans[stu]) for stu in students},
    }


# ---------- 报告渲染 ----------

def _fmt_obs(entry):
    obs = entry["obs"]
    bits = []
    if obs["group"]:
        bits.append(f"小组{obs['group']}")
    bits.append(f"场合{obs['occasion']}")
    if entry["ruling"]:
        bits.append(f"第{entry['ruling']['day']}日确认")
    return f"{obs['observation']}（{'，'.join(bits)}）"


def render(analysis):
    tables = analysis["tables"]
    term = analysis["term"]
    verified = analysis["verified"]
    plans = analysis["plans"]
    enroll = analysis["enroll"]
    tally = analysis["tally"]
    dist = analysis["distribution"]
    comps = analysis["comparisons"]
    goals = {g["goal"]: g for g in tables["goals"]}
    sections = {s["section"]: s for s in tables["sections"]}
    workshops = {w["session"]: w for w in tables["workshops"]}
    advisors = {a["student"]: a["advisor"] for a in tables["admissions"]}
    lines = []
    lines.append(f"跨学期写作辅导安排报告（当前学期 {term}，日序以业务日计）")

    lines.append("")
    lines.append("【一】当期目标认定（只计已认可证据）")
    for stu, plan in plans.items():
        adm = plan["admission"]
        lines.append(f"{stu}（注册要求：{adm['required']}，第{adm['start_day']}日开课，"
                     f"负责：{adm['advisor']}）")
        for g in plan["relevant"]:
            st = plan["status"][g]
            if st["met"]:
                obs = "、".join(_fmt_obs(e) for e in st["accepted"])
                lines.append(f"  {g}：达标 —— 认可 {obs}")
                continue
            cause = GAP_LABELS[gap_cause(st)]
            parts = [f"  {g}：未达标 —— {cause}"]
            parts.append(f"隔次 {st['occasions_have']}/{st['occasions_need']}")
            for path, det in sorted(st["paths"].items()):
                if det["missing"]:
                    parts.append(f"先修路径{path}缺：{'、'.join(det['missing'])}")
                else:
                    parts.append(f"先修路径{path}已通")
            notes = []
            for e in st["assisted"]:
                notes.append(f"{e['obs']['observation']}为辅助完成，仅作教学")
            for e in st["disputed"]:
                chain = ruling_chain(tables, e["obs"]["observation"], stu)
                hist = "→".join(f"{r['state']}({r['day']})" for r in chain)
                notes.append(f"{e['obs']['observation']}确认链 {hist}")
            for e in st["expired"]:
                notes.append(f"{e['obs']['observation']}超出有效期")
            if notes:
                parts.append("；".join(notes))
            lines.append("；".join(parts))

    lines.append("")
    lines.append("【二】下周辅导建议")
    for stu, plan in plans.items():
        adm = plan["admission"]
        if not plan["steps"] and not plan["shortfalls"]:
            lines.append(f"{stu}：无待补缺口")
            continue
        lines.append(f"{stu}：")
        for step in plan["steps"]:
            tag = "保留已约" if step["kept_booking"] else "新约"
            w = workshops[step["session"]]
            line = (f"  {tag} {step['session']}（第{step['day']}日练，"
                    f"第{step['verified']}日确认）→ "
                    f"{'、'.join(step['goals'])}")
            if w["verified"] != step["verified"]:
                line += f"；确认日已经教师变更（原第{w['verified']}日）"
            if step["verified"] == adm["start_day"]:
                line += f"；确认日与开课日相同，须{adm['advisor']}老师当日盯办"
            lines.append(line)
        for audit in analysis["audits"][stu]:
            if not audit["applicable"]:
                lines.append(f"  已约 {audit['session']} 不再适用，"
                             f"提示{adm['advisor']}老师改约，不悄悄换人")
        for sf in plan["shortfalls"]:
            why = []
            for r in sf["rejected"]:
                why.append(f"{r['session']}：{'、'.join(r['why'])}")
            detail = "；".join(why) if why else "无覆盖该目标的练习"
            lines.append(f"  断档 {sf['goal']}：仍缺 {sf['lacking']} 次隔次 —— {detail}")
        verify = []
        for step in plan["steps"]:
            for g in step["goals"]:
                have = plan["status"][g]["occasions_have"]
                need = plan["status"][g]["occasions_need"]
                verify.append(f"{step['session']}须产生{g}独立观察"
                              f"（现{have}/{need}次隔次）")
        if verify:
            lines.append(f"  下次辅导须验证：{'；'.join(verify)}")

    lines.append("")
    lines.append("【三】班组进展分布（预测不计入已学会）")
    lines.append("目标　　已达标　待核实(计划已齐)　部分证据　无法按期")
    for g, buckets in dist.items():
        def names(key):
            return "、".join(buckets[key]) or "—"
        lines.append(f"{g}　{names('met')}　{names('planned')}　"
                     f"{names('partial')}　{names('blocked')}")

    lines.append("")
    lines.append("【四】有条件选课（每人只承诺一个正式班次；候补不占容量）")
    for stu, plan in plans.items():
        adm = plan["admission"]
        en = enroll[stu]
        lines.append(f"{stu}：")
        for row in en["existing"]:
            if row["verdict"] == "作废":
                lines.append(f"  既有 {row['section']} 条件名额作废 —— "
                             f"要求{sections[row['section']]['requirement']}无完整路径，"
                             f"联系{row['advisor']}老师改约，不得继续算先修通过")
            elif row["verdict"] == "维持":
                lines.append(f"  既有 {row['section']} 条件名额维持，如期核实后转正式")
            else:
                note = "；该要求目前无完整路径，兑现无望需知悉" \
                    if not row["reachable"] else ""
                lines.append(f"  既有 {row['section']} 候补保留（不占正式班容量）{note}")
        for p in plan["preference"]:
            offer = en["offers"].get(p)
            if not offer:
                continue
            if offer["kind"] == "official":
                lines.append(f"  {p}：要求{offer['req']}已达标，可给正式名额")
            elif offer["kind"] == "conditional":
                used = "、".join(st["session"] for st in offer["steps"]) or "—"
                latest = max((st["verified"] for st in offer["steps"]), default=None)
                lines.append(f"  {p}：可给条件名额 —— 要求{offer['req']}未达，"
                             f"路径 {used}，最迟第{latest}日确认，"
                             f"不晚于改选截止第{sections[p]['switch_until']}日")
            elif offer["reason"] == "late":
                lines.append(f"  {p}：不可行 —— 确认最晚第{offer['latest']}日完成，"
                             f"晚于改选截止第{offer['deadline']}日")
            else:
                bits = []
                for b in offer["blockers"]:
                    if b["contested"]:
                        bits.append(f"{b['goal']}证据争议未决，不得以估计达标先入课")
                    elif b["shortfall"]:
                        bits.append(f"{b['goal']}无完整路径")
                    else:
                        bits.append(f"{b['goal']}未达")
                lines.append(f"  {p}：不可行 —— {'；'.join(bits)}")
        if en["commitment"]:
            lines.append(f"  正式承诺：{en['commitment']}"
                         f"（{'条件' if en['offers'].get(en['commitment'], {}).get('kind') != 'official' else '正式'}名额）")
        else:
            lines.append("  正式承诺：无")
        if plan["after"][adm["required"]]["met"] is False:
            lines.append(f"  注册要求{adm['required']}本期无法完成，"
                         f"须{adm['advisor']}老师介入安排改课")
    lines.append("班次容量：")
    for s, sec in sorted(sections.items()):
        t = tally[s]
        used = len(t["conditional"]) + len(t["official"])
        bits = [f"{s} 条件{len(t['conditional'])}+正式{len(t['official'])}/{sec['seats']}"]
        if t["waiting"]:
            bits.append(f"候补{len(t['waiting'])}（不占容量）")
        if t["voided"]:
            bits.append(f"作废{len(t['voided'])}")
        if used > sec["seats"]:
            bits.append("超容量！")
        lines.append("  " + "；".join(bits))

    lines.append("")
    lines.append("【五】回查（建议 ← 认可记录 / 仍缺条件 / 为何不适用于相似同学）")
    for stu, plan in plans.items():
        if not plan["steps"]:
            continue
        lines.append(f"{stu}：")
        for step in plan["steps"]:
            for g in step["goals"]:
                st = plan["status"][g]
                acc = "、".join(_fmt_obs(e) for e in st["accepted"]) or "无"
                lines.append(f"  {step['session']}→{g}：已认可 {acc}；"
                             f"隔次 {st['occasions_have']}/{st['occasions_need']}")
                for e in st["disputed"]:
                    chain = ruling_chain(tables, e["obs"]["observation"], stu)
                    hist = "→".join(f"{r['state']}({r['day']})" for r in chain)
                    lines.append(f"    证据相冲路径：{e['obs']['observation']} "
                                 f"确认链 {hist}，须{advisors[stu]}老师裁定，"
                                 f"新观察须独立场合重新取得")
                for e in st["assisted"]:
                    lines.append(f"    纯缺记录路径：{e['obs']['observation']}为辅助完成，"
                                 f"仅作教学，直接预约独立场合补观察")
                for other, reasons in comps.get((stu, step["session"], g), []):
                    lines.append(f"    同款建议不适用于 {other}：{'、'.join(reasons)}")
    return "\n".join(lines)


def main(argv):
    folder = Path(argv[1]) if len(argv) > 1 else ROOT
    print(render(analyze(folder)))


if __name__ == "__main__":
    main(sys.argv)

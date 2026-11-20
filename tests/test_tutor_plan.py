import unittest

from record_reader import read_records
import tutor_plan as tp


class GoalStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = read_records()
        cls.term = tp.current_term(cls.tables)

    def status(self, student, term=None):
        return tp.goal_status(self.tables, student, term or self.term)

    def test_same_occasion_counts_once(self):
        # o3（短文）与 o4（口述）同处场合 c，只算一次隔次观察
        st = self.status("s1")["反例修正"]
        self.assertEqual(st["occasions_have"], 1)
        self.assertFalse(st["met"])

    def test_group_record_needs_individual_ruling(self):
        # o2 是小组记录，s1 有本人追认计入，s2 无追认不计入
        s1 = self.status("s1")["口述反驳"]
        self.assertTrue(s1["met"])
        self.assertEqual([e["obs"]["observation"] for e in s1["accepted"]], ["o2"])
        s2 = self.status("s2")["口述反驳"]
        self.assertEqual([e["obs"]["observation"] for e in s2["accepted"]], ["o6"])

    def test_assisted_observation_does_not_settle_independent_goal(self):
        # o5 经辅助完成，只能教学，不能结清独立目标
        st = self.status("s1")["反例修正"]
        self.assertEqual([e["obs"]["observation"] for e in st["assisted"]], ["o5"])
        self.assertEqual(st["occasions_have"], 1)

    def test_latest_ruling_wins(self):
        # o8 经历 accept→contested→reject，以最新否定为准
        st = self.status("s2")["反例修正"]
        self.assertEqual(st["occasions_have"], 1)
        self.assertEqual(st["disputed"][0]["ruling"]["state"], "reject")

    def test_alternate_prereq_paths(self):
        # 反例修正先修：s1 两条路径都通，s2 只走通课堂路
        s1 = self.status("s1")["反例修正"]
        self.assertTrue(s1["prereq_ok"])
        self.assertEqual(s1["paths"]["证据路"]["missing"], [])
        self.assertEqual(s1["paths"]["课堂路"]["missing"], [])
        s2 = self.status("s2")["反例修正"]
        self.assertTrue(s2["prereq_ok"])
        self.assertEqual(s2["paths"]["证据路"]["missing"], ["论据"])
        self.assertEqual(s2["paths"]["课堂路"]["missing"], [])

    def test_prereq_blocks_goal_despite_accepted_observation(self):
        # s2 的结构写作观察 o9 已认可，但先修反例修正未满
        st = self.status("s2")["结构写作"]
        self.assertTrue(st["own_ok"])
        self.assertFalse(st["prereq_ok"])
        self.assertFalse(st["met"])

    def test_cross_format_observation_does_not_leak(self):
        # x2 只对应口述反驳，不能充作反例修正的场合
        st = self.status("s2")["反例修正"]
        self.assertNotIn("e", {e["obs"]["occasion"] for e in st["accepted"]})

    def test_term_validity(self):
        # 论据 valid_terms=2：第 1 学期证据在第 2 学期有效，第 3 学期超期
        self.assertTrue(self.status("s1", term=2)["论据"]["met"])
        expired = self.status("s1", term=3)["论据"]
        self.assertFalse(expired["met"])
        self.assertEqual(len(expired["expired"]), 1)


class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = tp.analyze()
        cls.plans = cls.analysis["plans"]

    def test_adjustments_shift_verified_day(self):
        self.assertEqual(self.analysis["verified"]["w2"], 40)
        self.assertEqual(self.analysis["verified"]["w3"], 44)

    def test_s1_plan_books_earliest_in_time_sessions(self):
        steps = self.plans["s1"]["steps"]
        self.assertEqual([s["session"] for s in steps], ["w1", "w2"])
        self.assertEqual(steps[0]["goals"], ["反例修正"])
        self.assertEqual(steps[1]["goals"], ["结构写作"])
        self.assertTrue(all(s["verified"] <= 40 for s in steps))

    def test_s2_keeps_existing_booking(self):
        steps = self.plans["s2"]["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["session"], "w2")
        self.assertTrue(steps[0]["kept_booking"])
        audit = self.analysis["audits"]["s2"][0]
        self.assertTrue(audit["applicable"])

    def test_s3_only_argument_session_reachable(self):
        plan = self.plans["s3"]
        self.assertEqual([s["session"] for s in plan["steps"]], ["w5"])
        short = {s["goal"] for s in plan["shortfalls"]}
        self.assertIn("反例修正", short)
        self.assertIn("结构写作", short)

    def test_non_independent_workshop_rejected(self):
        # w4 非独立，不能结清独立的口述反驳
        sf = next(s for s in self.plans["s3"]["shortfalls"] if s["goal"] == "口述反驳")
        w4 = next(r for r in sf["rejected"] if r["session"] == "w4")
        self.assertTrue(any("非独立" in w for w in w4["why"]))

    def test_workshop_capacity_accounts_appointments(self):
        # w2 容量 2：s2 已约 + s1 新约 = 满
        self.assertEqual(self.analysis["seats_left"]["w2"], 0)
        self.assertEqual(self.analysis["seats_left"]["w5"], 1)

    def test_one_session_does_not_double_count_occasions(self):
        # s1 反例修正计划后场合为 {c, w1}，w2 不再重复计入
        after = self.plans["s1"]["after"]["反例修正"]
        self.assertEqual(after["occasions_have"], 2)


class EnrollmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = tp.analyze()
        cls.enroll = cls.analysis["enroll"]
        cls.tally = cls.analysis["tally"]

    def test_s1_k1_too_late_k2_conditional(self):
        en = self.enroll["s1"]
        self.assertEqual(en["offers"]["k1"]["reason"], "late")
        self.assertEqual(en["offers"]["k2"]["kind"], "conditional")
        self.assertEqual(en["commitment"], "k2")

    def test_s2_k3_voided_and_k2_committed(self):
        en = self.enroll["s2"]
        self.assertEqual(en["offers"]["k3"]["reason"], "unreachable")
        voided = [r for r in en["existing"]
                  if r["section"] == "k3" and r["verdict"] == "作废"]
        self.assertEqual(len(voided), 1)
        self.assertEqual(en["commitment"], "k2")
        waiting = [r for r in en["existing"] if r["section"] == "k4"]
        self.assertEqual(waiting[0]["verdict"], "保留候补")
        self.assertFalse(waiting[0]["reachable"])

    def test_s3_conditional_k4(self):
        en = self.enroll["s3"]
        self.assertEqual(en["offers"]["k2"]["reason"], "unreachable")
        self.assertEqual(en["offers"]["k4"]["kind"], "conditional")
        self.assertEqual(en["commitment"], "k4")

    def test_one_commitment_per_student(self):
        # 班次台账中，每名学生至多出现在一个正式/条件承诺里
        seen = {}
        for section, t in self.tally.items():
            for stu in t["conditional"] + t["official"]:
                self.assertNotIn(stu, seen, f"{stu} 出现多个正式承诺")
                seen[stu] = section
        for stu, en in self.enroll.items():
            if en["commitment"]:
                self.assertEqual(seen.get(stu), en["commitment"])

    def test_waiting_does_not_consume_seat(self):
        self.assertEqual(len(self.tally["k4"]["conditional"]), 1)  # s3
        self.assertEqual(self.tally["k4"]["waiting"], ["s2"])
        self.assertEqual(len(self.tally["k2"]["conditional"]), 2)  # s1, s2 恰好满
        self.assertEqual(self.tally["k3"]["voided"], ["s2"])

    def test_distribution_does_not_count_predictions_as_learned(self):
        dist = self.analysis["distribution"]
        self.assertEqual(dist["反例修正"]["met"], [])
        self.assertEqual(sorted(dist["反例修正"]["planned"]), ["s1", "s2"])
        self.assertEqual(dist["结构写作"]["met"], [])
        self.assertEqual(sorted(dist["结构写作"]["planned"]), ["s1", "s2"])
        self.assertEqual(dist["论据"]["met"], ["s1"])


class TracebackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = tp.analyze()

    def test_same_advice_not_for_classmate(self):
        comps = self.analysis["comparisons"]
        # w5 论据建议给 s3，不适用于 s2（第 38 日不可到）
        hit = comps[("s3", "w5", "论据")]
        self.assertEqual(hit[0][0], "s2")
        self.assertTrue(any("不可到" in r for r in hit[0][1]))
        # w2 结构写作建议给 s1，不适用于 s3
        hit = comps[("s1", "w2", "结构写作")]
        self.assertEqual(hit[0][0], "s3")

    def test_gap_cause_distinguishes_missing_vs_contradicted(self):
        plans = self.analysis["plans"]
        # s1 反例修正：隔次不足且有辅助记录（纯缺记录路径）
        st1 = plans["s1"]["status"]["反例修正"]
        self.assertEqual(tp.gap_cause(st1), "missing_occasion")
        self.assertEqual(len(st1["assisted"]), 1)
        self.assertEqual(len(st1["disputed"]), 0)
        # s2 反例修正：隔次不足且有被否定记录（证据相冲路径）
        st2 = plans["s2"]["status"]["反例修正"]
        self.assertEqual(tp.gap_cause(st2), "missing_occasion")
        self.assertEqual(len(st2["disputed"]), 1)

    def test_render_runs(self):
        text = tp.render(self.analysis)
        for needle in ("【一】", "【二】", "【三】", "【四】", "【五】", "k3", "作废"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()

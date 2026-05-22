import unittest

from config import ai_knowledge as K


class KnowledgeFragmentsTest(unittest.TestCase):
    def test_field_guide_present(self):
        self.assertIn("rise_ratio", K.FIELD_GUIDE)
        self.assertIn("broken_board_count", K.FIELD_GUIDE)

    def test_emotion_indicators_present(self):
        self.assertIn("六大情绪指标", K.EMOTION_INDICATORS)
        self.assertIn("打板成功率", K.EMOTION_INDICATORS)

    def test_emotion_stages_present(self):
        for stage in ("冰点期", "修复期", "升温期", "高潮期", "退潮期"):
            self.assertIn(stage, K.EMOTION_STAGES)

    def test_position_table_unified(self):
        # 升温期统一为 6-8 成,旧的 5-7 成口径不得残留
        self.assertIn("6-8成", K.POSITION_TABLE)
        self.assertNotIn("5-7成", K.POSITION_TABLE)
        self.assertNotIn("5-7成", K.EMOTION_STAGES)


class TacticsTest(unittest.TestCase):
    EXPECTED = [
        "龙头首阴低吸", "爆量涨停弱转强", "首板一进二",
        "打板接力", "断板反包", "龙回头", "中军补涨",
    ]

    def test_seven_tactics(self):
        self.assertEqual(len(K.TACTICS), 7)
        for key in self.EXPECTED:
            self.assertIn(key, K.TACTICS)

    def test_tactic_has_brief_and_full(self):
        for key, tac in K.TACTICS.items():
            self.assertTrue(tac.brief, f"{key} brief 为空")
            self.assertTrue(tac.full, f"{key} full 为空")
            self.assertTrue(len(tac.full) > len(tac.brief), f"{key} full 应比 brief 长")

    def test_tactics_brief_has_adapt_table(self):
        self.assertIn("情绪适配", K.TACTICS_BRIEF)
        for stage in ("冰点期", "升温期", "退潮期"):
            self.assertIn(stage, K.TACTICS_BRIEF)

    def test_tactics_full_covers_all(self):
        for tac in K.TACTICS.values():
            self.assertIn(tac.full, K.TACTICS_FULL)
        self.assertIn("没有永恒有效的战法", K.TACTICS_FULL)


class PromptCompositionTest(unittest.TestCase):
    def test_system_prompt_uses_fragments(self):
        from config import ai_prompts as P
        self.assertIn("broken_board_count", P.SYSTEM_PROMPT)   # FIELD_GUIDE
        self.assertIn("六大情绪指标", P.SYSTEM_PROMPT)          # EMOTION_INDICATORS
        self.assertIn("龙回头", P.SYSTEM_PROMPT)               # TACTICS_BRIEF
        self.assertIn("\"stage\"", P.SYSTEM_PROMPT)            # JSON schema 保留

    def test_no_stale_position_value(self):
        from config import ai_prompts as P
        # 旧的不一致仓位口径不得残留
        self.assertNotIn("5-7成", P.SYSTEM_PROMPT)
        self.assertNotIn("5-7成", P.BATCH_ANALYSIS_PROMPT)

    def test_single_date_keeps_placeholder(self):
        from config import ai_prompts as P
        self.assertIn("{FIELD_GUIDE}", P.SINGLE_DATE_ANALYSIS_PROMPT)


class DiagnosisTemplateTest(unittest.TestCase):
    def test_template_embeds_tactics(self):
        from config import ai_prompts as P
        self.assertIn("七大超短战法", P.DIAGNOSIS_REPORT_TEMPLATE)

    def test_template_has_new_fields(self):
        from config import ai_prompts as P
        self.assertIn("applicable_tactic", P.DIAGNOSIS_REPORT_TEMPLATE)
        self.assertIn("tactic_fit", P.DIAGNOSIS_REPORT_TEMPLATE)

    def test_build_diagnosis_prompt_keeps_fields(self):
        from config.ai_prompts import build_diagnosis_prompt
        s = build_diagnosis_prompt({"code": "000001"})
        self.assertIn("000001", s)
        self.assertIn("applicable_tactic", s)
        self.assertIn("tactic_fit", s)


class AgentSkillsTest(unittest.TestCase):
    def test_four_skills_registered(self):
        from config.ai_prompts import AGENT_SKILLS
        self.assertEqual(
            set(AGENT_SKILLS),
            {"stock-analysis", "market-sentiment", "board-hitting", "trading-patterns"},
        )

    def test_trading_patterns_body_has_seven_tactics(self):
        from config.ai_prompts import AGENT_SKILLS
        body = AGENT_SKILLS["trading-patterns"]["body"]
        for name in ("打板", "断板反包", "龙回头", "中军补涨"):
            self.assertIn(name, body)

    def test_skill_step1_data_wording(self):
        from config.ai_prompts import AGENT_SKILLS
        body = AGENT_SKILLS["stock-analysis"]["body"]
        # 结构化数据优先用 MCP，WebSearch 仅补消息面
        self.assertIn("禁止编造", body)

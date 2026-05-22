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

import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from routes.limit_up_echelon import _default_echelon_dt, _parse_grouping_json, get_limit_up_echelon


class DefaultEchelonDtTest(unittest.TestCase):
    def test_sunday_defaults_to_friday(self):
        with patch('routes.limit_up_echelon.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 17, 12, 0, 0)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            self.assertEqual(_default_echelon_dt(), '20260515')


class LimitUpEchelonGroupingTest(unittest.TestCase):
    def test_parse_group_array_with_reasons_and_stock_members(self):
        content = """
        {
          "groups": [
            {
              "label": "机器人",
              "reason": "特斯拉Optimus量产催化",
              "leaders": [
                {"code": "002031", "name": "巨轮智能", "role": "先锋龙", "reason": "高标连板且辨识度最高"},
                {"code": "300276", "name": "三丰智能", "role": "中军", "reason": "容量辨识度较高"}
              ],
              "stocks": [
                {"code": "002031", "name": "巨轮智能", "why": "机器人减速器"},
                {"code": "300276", "name": "三丰智能", "why": "人形机器人"}
              ]
            },
            {
              "label": "氟化工",
              "reason": "氢氟酸涨价",
              "stocks": [
                {"code": "002407", "name": "多氟多", "why": "氟化工龙头"}
              ]
            }
          ]
        }
        """

        parsed = _parse_grouping_json(content)

        self.assertEqual(parsed["labels"]["002031"], "机器人")
        self.assertEqual(parsed["labels"]["300276"], "机器人")
        self.assertEqual(parsed["labels"]["002407"], "氟化工")
        self.assertEqual(parsed["reasons"]["机器人"], "特斯拉Optimus量产催化")
        self.assertEqual(parsed["reasons"]["氟化工"], "氢氟酸涨价")
        self.assertEqual(parsed["leaders"]["机器人"][0]["code"], "002031")
        self.assertEqual(parsed["leaders"]["机器人"][0]["name"], "巨轮智能")
        self.assertEqual(parsed["leaders"]["机器人"][0]["role"], "先锋龙")
        self.assertEqual(parsed["leaders"]["机器人"][1]["code"], "300276")
        self.assertEqual(parsed["leaders"]["机器人"][1]["role"], "中军")


class GetLimitUpEchelonApiTest(unittest.TestCase):
    @patch("routes.limit_up_echelon._echelon_response_from_db")
    def test_reads_from_db_only(self, mock_db):
        from app import app

        mock_db.return_value = {
            "echelons": [{"boards": 1, "count": 1, "stocks": []}],
            "summary": {"total": 1},
        }
        with app.test_client() as client:
            resp = client.get("/api/v1/limit-up-echelon?dt=2026-05-15")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["success"])
        mock_db.assert_called_once_with("20260515", "2026-05-15")


class RuleHintTest(unittest.TestCase):
    def test_hint_robot_and_fluorine(self):
        from routes.limit_up_echelon import _assign_broad_tag_from_stock

        self.assertEqual(
            _assign_broad_tag_from_stock({
                "name": "巨轮智能", "industry": "专用设备",
                "ths_analyse_title": "人形机器人+RV减速器",
                "stock_concept_tags": ["减速器", "人形机器人"],
            }),
            "机器人",
        )
        self.assertEqual(
            _assign_broad_tag_from_stock({
                "name": "多氟多", "industry": "化学制品",
                "ths_analyse_title": "氢氟酸涨价",
                "stock_concept_tags": ["氟化工概念"],
            }),
            "电子特气/化工",
        )
        # 单字「消费」不足以判大消费
        self.assertEqual(
            _hint_label_from_stock({
                "name": "某股", "industry": "软件",
                "ths_analyse_title": "消费复苏预期",
                "ths_concept_tags": [],
            }),
            "",
        )


class StockConceptWeightTest(unittest.TestCase):
    def test_merge_em_and_ths_concepts(self):
        from routes.limit_up_echelon import _merge_stock_concept_tags

        merged = _merge_stock_concept_tags(
            {"em_concept_tags": ["人形机器人", "减速器"]},
            {"concept_tags": ["减速器", "专精特新"]},
        )
        self.assertEqual(merged, ["人形机器人", "减速器", "专精特新"])

    def test_label_overlap_prefers_stock_concepts(self):
        from routes.limit_up_echelon import _label_text_overlap

        stock = {
            "stock_concept_tags": ["光通信", "CPO"],
            "industry": "通信设备",
            "ths_analyse_title": "电力转型",
        }
        self.assertGreater(
            _label_text_overlap("光通信", stock),
            _label_text_overlap("电力", stock),
        )


class FinalizeGroupLabelsTest(unittest.TestCase):
    def test_merges_single_stock_tag_without_forcing_canonical(self):
        from routes.limit_up_echelon import _finalize_group_labels

        labels = {
            "000001": "光通信",
            "000002": "光通信",
            "000003": "孤立题材",
        }
        stocks = [
            {"code": "000001", "name": "A", "ths_analyse_title": "光通信模块"},
            {"code": "000002", "name": "B", "ths_analyse_title": "光通信"},
            {"code": "000003", "name": "C", "ths_analyse_title": "光通信测试"},
        ]
        result = _finalize_group_labels(
            {"labels": labels, "reasons": {}, "leaders": {}},
            stocks,
        )
        self.assertEqual(result["labels"]["000001"], "光通信")
        self.assertIn(result["labels"]["000003"], ("光通信", "其他概念"))


class EnforceGroupLimitsTest(unittest.TestCase):
    def test_caps_tag_count_and_other_bucket(self):
        from routes.limit_up_echelon import _enforce_group_limits, MAX_DAY_TAGS, MAX_OTHER_STOCKS

        broad = ["机器人", "氟化工", "大消费", "电力", "光伏", "光通信"]
        labels = {}
        for i in range(12):
            labels[f"{i:06d}"] = broad[i % len(broad)]
        for i in range(12, 12 + MAX_OTHER_STOCKS + 3):
            labels[f"{i:06d}"] = "其他概念"
        stocks = [{"code": c} for c in labels]
        result = _enforce_group_limits({"labels": labels, "reasons": {}, "leaders": {}}, stocks)
        tag_set = set(result["labels"].values())
        self.assertLessEqual(len(tag_set), MAX_DAY_TAGS)
        other_count = sum(1 for l in result["labels"].values() if l == "其他概念")
        self.assertLessEqual(other_count, MAX_OTHER_STOCKS)


class SmartGroupRegroupTest(unittest.TestCase):
    @patch("routes.limit_up_echelon._call_claude")
    @patch("routes.limit_up_echelon.get_limit_up_stocks_by_date")
    @patch("routes.limit_up_echelon.get_tags_by_date")
    @patch("routes.limit_up_echelon.date_has_manual_tags", return_value=False)
    def test_skip_regroup_when_all_tags_from_db(self, _manual, mock_tags, mock_stocks, mock_claude):
        from routes.limit_up_echelon import _smart_group_stocks

        mock_stocks.return_value = [
            {"code": "000001", "tag_name": "其他概念"},
            {"code": "000002", "tag_name": "其他概念"},
        ]
        mock_tags.return_value = [{"tag_name": "其他概念", "reason": ""}]
        stocks = [
            {"code": "000001", "name": "A", "boards": 1},
            {"code": "000002", "name": "B", "boards": 1},
        ]
        result = _smart_group_stocks(stocks, "20260515")
        self.assertEqual(result["labels"]["000001"], "其他概念")
        mock_claude.assert_not_called()


class BuildEchelonOneDateTest(unittest.TestCase):
    @patch("routes.limit_up_echelon.date_has_manual_tags", return_value=False)
    @patch("routes.limit_up_echelon.save_ai_grouping_result")
    @patch("routes.limit_up_echelon._smart_group_stocks")
    @patch("routes.limit_up_echelon._fetch_zt_pool_and_ths")
    @patch("routes.limit_up_echelon._echelon_grouping_complete", return_value=False)
    def test_saved_when_grouping_ok(self, _complete, mock_fetch, mock_group, mock_save, _manual):
        import pandas as pd
        from routes.limit_up_echelon import build_echelon_one_date

        df = pd.DataFrame([{"代码": "000001", "名称": "测试", "连板数": 1, "成交额": 1, "封板资金": 1,
                            "最新价": 10, "涨跌幅": 10, "流通市值": 1, "换手率": 1,
                            "首次封板时间": "093000", "最后封板时间": "093000", "炸板次数": 0,
                            "所属行业": "测试", "涨停统计": "1/1"}])
        mock_fetch.return_value = (df, [], {})
        mock_group.return_value = {"labels": {"000001": "机器人"}, "reasons": {}, "leaders": {}}

        result = build_echelon_one_date("20260515", force=False)
        self.assertEqual(result, "saved")
        mock_save.assert_called_once()

    @patch("routes.limit_up_echelon.date_has_manual_tags", return_value=False)
    @patch("routes.limit_up_echelon._echelon_grouping_complete", return_value=True)
    def test_skipped_when_already_in_db(self, _complete, _manual):
        from routes.limit_up_echelon import build_echelon_one_date
        self.assertEqual(build_echelon_one_date("20260515", force=False), "skipped")


if __name__ == "__main__":
    unittest.main()

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


class NormalizeBroadTagsTest(unittest.TestCase):
    def test_merges_fine_tags_into_canonical(self):
        from routes.limit_up_echelon import _normalize_to_broad_tags

        labels = {
            "000001": "汽车零部件",
            "000002": "工业自动化",
            "000003": "绿电",
            "000004": "消费食品",
        }
        result = _normalize_to_broad_tags(
            {"labels": labels, "reasons": {}, "leaders": {}},
            [{"code": c} for c in labels],
        )
        self.assertEqual(result["labels"]["000001"], "机器人")
        self.assertEqual(result["labels"]["000003"], "电力")
        self.assertEqual(result["labels"]["000004"], "大消费")


class EnforceGroupLimitsTest(unittest.TestCase):
    def test_caps_tag_count_and_other_bucket(self):
        from routes.limit_up_echelon import _enforce_group_limits, MAX_DAY_TAGS, MAX_OTHER_STOCKS

        labels = {}
        for i in range(12):
            labels[f"{i:06d}"] = f"题材{i}"
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

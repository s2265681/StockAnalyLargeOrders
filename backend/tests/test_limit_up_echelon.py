import unittest

from routes.limit_up_echelon import _parse_grouping_json


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


if __name__ == "__main__":
    unittest.main()

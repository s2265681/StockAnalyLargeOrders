"""
东方财富L2付费数据源（预留）
开通L2后实现具体逻辑，替换免费数据源
"""
import logging

logger = logging.getLogger(__name__)


class EastMoneyL2Source:
    """东方财富L2付费数据源

    与 EastMoneyFreeSource 相同的方法签名。
    开通L2（约30元/月）后实现以下方法即可切换。
    """

    def get_realtime_quote(self, code):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

    def get_tick_details(self, code, pos=-100000, dt=None):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

    def get_timeshare(self, code, dt=None):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

    def get_daily_kline(self, code, dt):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

    def infer_direction(self, buy_sell_type):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

"""
东方财富 L2 付费数据源（预留）
未单独实现时继承免费源，避免 use_l2=True 时接口直接崩溃。
"""
import logging

from .eastmoney_free import EastMoneyFreeSource

logger = logging.getLogger(__name__)


class EastMoneyL2Source(EastMoneyFreeSource):
    """L2 占位：开通后可在此类覆盖逐笔/盘口等方法；当前回退免费接口。"""

    def __init__(self):
        super().__init__()
        logger.debug("EastMoneyL2Source 使用免费接口回退（L2 尚未单独实现）")

"""
题材标签管理接口
- GET  /api/v1/themes                    获取指定日期的题材标签
- PUT  /api/v1/themes                    修改/新增/删除题材标签
- PUT  /api/v1/themes/stock              修改单只股票的题材归属
- PUT  /api/v1/themes/rename             重命名题材标签
- GET  /api/v1/limit-up-echelon/history  查历史涨停数据（从数据库）
"""
import logging
from collections import Counter
from datetime import datetime

from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from services.theme_service import (
    get_tags_by_date,
    upsert_tag,
    delete_tag,
    rename_tag,
    update_stock_tag,
    load_echelon_from_db,
    get_limit_up_stocks_by_date,
)

logger = logging.getLogger(__name__)

theme_manage_bp = Blueprint('theme_manage', __name__)


@theme_manage_bp.route('/api/v1/themes', methods=['GET'])
def get_themes():
    """获取指定日期的题材标签列表"""
    date = request.args.get('date', datetime.now().strftime('%Y%m%d')).replace('-', '')
    try:
        tags = get_tags_by_date(date)
        # 同时获取每个标签下的股票数量
        stocks = get_limit_up_stocks_by_date(date)
        tag_counter = Counter(s["tag_name"] for s in stocks if s.get("tag_name"))
        for t in tags:
            t["stock_count"] = tag_counter.get(t["tag_name"], 0)
        return v1_success_response(data={"date": date, "tags": tags})
    except Exception as e:
        logger.error(f"获取题材标签失败: {e}", exc_info=True)
        return v1_error_response(message=f"获取题材标签失败: {str(e)}")


@theme_manage_bp.route('/api/v1/themes', methods=['PUT'])
def update_themes():
    """修改题材标签
    Body:
    - action: "add" | "update" | "delete"
    - date: "20250516"
    - tag_name: "机器人"
    - reason: "..." (add/update 时)
    """
    try:
        body = request.get_json(silent=True) or {}
        action = body.get("action", "update")
        date = body.get("date", datetime.now().strftime('%Y%m%d')).replace('-', '')
        tag_name = (body.get("tag_name") or "").strip()

        if not tag_name:
            return v1_error_response(message="tag_name 不能为空")

        if action == "delete":
            delete_tag(date, tag_name)
            return v1_success_response(message=f"已删除标签: {tag_name}")
        else:
            reason = body.get("reason", "")
            source = body.get("source", "manual")
            upsert_tag(date, tag_name, reason, source)
            return v1_success_response(message=f"已{'新增' if action == 'add' else '更新'}标签: {tag_name}")

    except Exception as e:
        logger.error(f"修改题材标签失败: {e}", exc_info=True)
        return v1_error_response(message=f"修改题材标签失败: {str(e)}")


@theme_manage_bp.route('/api/v1/themes/rename', methods=['PUT'])
def rename_theme():
    """重命名题材标签（同时更新关联的股票和龙头）
    Body: {"date": "20250516", "old_name": "半导体", "new_name": "半导体产业链"}
    """
    try:
        body = request.get_json(silent=True) or {}
        date = body.get("date", datetime.now().strftime('%Y%m%d')).replace('-', '')
        old_name = (body.get("old_name") or "").strip()
        new_name = (body.get("new_name") or "").strip()

        if not old_name or not new_name:
            return v1_error_response(message="old_name 和 new_name 不能为空")

        rename_tag(date, old_name, new_name)
        return v1_success_response(message=f"已重命名: {old_name} -> {new_name}")

    except Exception as e:
        logger.error(f"重命名标签失败: {e}", exc_info=True)
        return v1_error_response(message=f"重命名标签失败: {str(e)}")


@theme_manage_bp.route('/api/v1/themes/stock', methods=['PUT'])
def update_stock_theme():
    """修改单只股票的题材归属
    Body: {"date": "20250516", "code": "002918", "tag_name": "半导体"}
    """
    try:
        body = request.get_json(silent=True) or {}
        date = body.get("date", datetime.now().strftime('%Y%m%d')).replace('-', '')
        code = (body.get("code") or "").strip()
        tag_name = (body.get("tag_name") or "").strip()

        if not code or not tag_name:
            return v1_error_response(message="code 和 tag_name 不能为空")

        update_stock_tag(date, code, tag_name)
        return v1_success_response(message=f"已将 {code} 归入 {tag_name}")

    except Exception as e:
        logger.error(f"修改股票题材失败: {e}", exc_info=True)
        return v1_error_response(message=f"修改股票题材失败: {str(e)}")


@theme_manage_bp.route('/api/v1/limit-up-echelon/history', methods=['GET'])
def get_echelon_history():
    """从数据库查询历史涨停梯队数据"""
    date = request.args.get('date', '').replace('-', '')
    if not date:
        return v1_error_response(message="请提供 date 参数")

    try:
        db_data = load_echelon_from_db(date)
        if not db_data:
            return v1_success_response(data={
                "echelons": [],
                "date": date,
                "theme_ranking": [],
                "ai": {"enabled": False, "cached": False, "ok": False},
                "summary": {"total": 0, "first_board_count": 0, "consec_count": 0, "max_boards": 0},
            })

        stocks = db_data["stocks"]
        theme_ranking = db_data["theme_ranking"]

        # 按连板数分组
        echelon_map = {}
        for s in stocks:
            echelon_map.setdefault(s["boards"], []).append(s)
        echelon_list = [
            {
                "boards": boards,
                "count": len(group),
                "stocks": sorted(group, key=lambda x: float(x.get("seal_amount") or 0), reverse=True),
            }
            for boards in sorted(echelon_map.keys(), reverse=True)
            for group in [echelon_map[boards]]
        ]

        total = len(stocks)
        first_board_count = sum(1 for s in stocks if s["boards"] == 1)

        return v1_success_response(data={
            "echelons": echelon_list,
            "date": date,
            "theme_ranking": theme_ranking,
            "ai": {"enabled": True, "cached": True, "ok": True, "status": "done"},
            "summary": {
                "total": total,
                "first_board_count": first_board_count,
                "consec_count": total - first_board_count,
                "max_boards": max((s["boards"] for s in stocks), default=0),
            },
            "ths_hot": [],
        })

    except Exception as e:
        logger.error(f"获取历史涨停数据失败: {e}", exc_info=True)
        return v1_error_response(message=f"获取历史数据失败: {str(e)}")

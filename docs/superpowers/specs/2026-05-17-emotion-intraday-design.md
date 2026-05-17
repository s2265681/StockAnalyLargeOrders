# 情绪周期双模块设计

## 模块1 · 周期研判（管理员）
- 接口：`POST /api/v1/emotion-analysis-with-storage`（`admin_required`）
- 存储：`analysis_result_json`
- 展示：随日期切换只读，`GET /api/v1/emotion-analysis-cache`

## 模块2 · 盘中研判（用户）
- 接口：`POST /api/v1/emotion-intraday-refresh`（`login_required`）
- 缓存：`GET /api/v1/emotion-intraday-cache?date=`
- 存储：`intraday_result_json`（同表，不覆盖 `analysis_result_json`）
- 流程：后端拉 StockAPI → 引用模块1 stage → 轻量单日 AI → 写库

## 前端
- 右侧双卡片：周期研判 + 盘中研判
- 管理员可见「全量生成」；所有用户可见「盘中刷新」（仅当日）

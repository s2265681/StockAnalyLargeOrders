# AI 诊股模块设计文档

**日期：** 2026-05-17  
**状态：** 已确认

---

## 概述

新增「AI诊股」页面：输入股票代码触发结构化诊股（综合 L2、大单、情绪周期、竞价抢筹、当天题材），支持基于报告的连续追问。后端接入 Claude（兼容现有环境变量），按 `date + code` 缓存当天结构化诊股结果；追问不持久化。

---

## 已确认决策

| 项 | 决策 |
|----|------|
| 架构 | 独立 Blueprint + 独立页面 |
| 交互 | 诊股报告 + 聊天追问 |
| 数据范围 | 核心版：行情/L2、大单、情绪、抢筹、题材 |
| Claude | 沿用 `CLAUDE_API_URL` / `CLAUDE_API_KEY` / `CLAUDE_MODEL` |
| 持久化 | 仅缓存当天结构化诊股；追问不存库 |
| 权限 | 登录即可（`RequireAuth`） |

---

## 数据库

### `ai_diagnosis_cache`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT PK | |
| date | VARCHAR(8) | YYYYMMDD |
| code | VARCHAR(6) | 股票代码 |
| snapshot_json | LONGTEXT | 聚合数据快照 |
| report_json | LONGTEXT | AI 结构化报告 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |
| UNIQUE | (date, code) | |

---

## API

- `POST /api/v1/ai-diagnosis` — Body: `{ code, force_refresh? }`
- `GET /api/v1/ai-diagnosis/cache?code=&date=` — 只读缓存
- `POST /api/v1/ai-diagnosis/chat` — Body: `{ code, message, context }`

---

## 前端

- 路由 `/ai-diagnosis`，导航「AI诊股」
- 页面：`frontend/src/pages/AiDiagnosis/`

---

## 文件清单

- `backend/routes/ai_diagnosis.py`
- `backend/services/ai_diagnosis_service.py`
- `backend/tests/test_ai_diagnosis.py`
- `frontend/src/pages/AiDiagnosis/index.js`
- `frontend/src/pages/AiDiagnosis/index.css`
- `frontend/src/App.js`（路由 + 菜单）

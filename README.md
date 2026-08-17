# Finance Core - v1.0.0

Finance Core（FC）是可复用、本地优先的个人财务领域与数据服务。它可以独立展示，也可以被 SFOS 等界面通过版本化 HTTP API 调用。

FC 不依赖 SFOS、Context Sources、OpenAI、Ollama 或任何 LLM。

## 能力与边界

```text
SFOS adapter / FC demo
        │
        ▼
FastAPI /api/v1
        │
deterministic domain + application operations
        │
SQLite adapter
```

FC 拥有：

- Journal transactions 与 account options
- Holdings
- Recurring rules 与到期生成命令
- Living accounts、balance snapshots 与 monthly plans
- Dashboard metrics、T-account、financial statements、reconciliation
- JSON/CSV import/export
- 10 分钟、单次使用、后续写入会使旧 token 失效的 operation-level undo
- 本地 SQLite

FC 不提供模型分析、投资建议、交易、支付、银行/券商连接或实时行情。

## 安装与运行

要求 Node.js、npm、Python 3.12 与 `uv`。

```powershell
cd S:\Codex-Projects\Finance-Core
npm.cmd install --offline
uv sync --project backend --cache-dir .tmp/uv-cache
```

启动 API 与独立只读演示 UI：

```powershell
npm.cmd run dev
```

- Demo：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8788`
- OpenAPI：`http://127.0.0.1:8788/docs`

也可只启动 API：

```powershell
npm.cmd run dev:api
```

## API v1

健康与兼容性：`GET /api/v1/health`

资源级 CRUD：

- `/api/v1/transactions`
- `/api/v1/holdings`
- `/api/v1/recurring-rules`
- `/api/v1/living-accounts`
- `/api/v1/living-snapshots`
- `/api/v1/monthly-plans`
- `/api/v1/account-options`

查询与命令：

- `GET /api/v1/dashboard`
- `GET /api/v1/t-accounts`
- `GET /api/v1/financial-statements`
- `GET /api/v1/reconciliation`
- `POST /api/v1/recurring-rules/generate-due`
- `POST /api/v1/living-accounts/{id}/record-balance`
- `POST /api/v1/undo`
- `POST /api/v1/batch`（SFOS 一次 UI 操作对应一个原子 batch 与一个 undo token）
- `GET /api/v1/export`
- `POST /api/v1/import`
- `GET /api/v1/export/{transactions|holdings}.csv`
- `POST /api/v1/import/{transactions|holdings}.csv`

兼容规则：Patch 只做兼容修复；Minor 可增加端点或可选字段；删除、重命名、改变 requiredness 或语义必须升级 Major。SFOS v0.5 的兼容范围为 `>=1.0.0 <2.0.0`。

## 数据迁移

先 dry-run：

```powershell
uv run --project backend python -m finance_core.migration --source '<legacy-sfos-db>'
```

真实迁移必须先停止旧写入进程、创建备份并获得 `REAL_DATA_MIGRATION_APPROVED`：

```powershell
uv run --project backend python -m finance_core.migration --source '<legacy-sfos-db>' --target '<new-fc-db>' --apply
```

脚本：

- 以 read-only 模式打开源数据库；
- 拒绝覆盖已有目标；
- 迁移财务实体；
- 不迁移 `knowledge_notes`、`validation_reports`、`analysis_reports`；
- 运行 `PRAGMA integrity_check` 与 `PRAGMA foreign_key_check`。

## 测试与构建

```powershell
npm.cmd test
npm.cmd run build
```

当前测试覆盖 API 版本、CRUD、单次撤销、账户选项撤销、确定性聚合、CSV、导出边界和迁移排除边界。全部使用合成数据与临时 SQLite。

## Codex 跨仓规则

每次修改必须输出统一影响区块。所有新需求只从一个仓库进入分诊：不知道归属时，只在一个仓库先用 `READ_ONLY` 询问，不要同时把同一需求发送给 SFOS 与 FC 两个 Codex 任务，也不要让它们并行、独立设计同一需求。面向产品或仍无法判断归属的需求默认从 SFOS 开始；明确属于通用财务领域的需求可以从 FC 开始。

分诊结果必须是以下三类之一：

- `SFOS_ONLY`：UI、导航、Context Sources、Context LLM、Inference LLM 或纯展示修改。
- `FC_ONLY`：财务实体、确定性计算、持久化、CSV、undo 或通用财务 API。
- `BOTH`：SFOS 需要新增或修改 FC contract。

`BOTH` 必须遵循 **FC first**：先在 FC 实现并用合成数据完成测试，确定兼容的 API 版本，再适配 SFOS；保留现有 FC → SFOS 的发布与适配顺序。不得因为另一仓库暂未实现所需能力，就在当前仓库创建本地替代实现。跨仓时必须生成可直接发送给另一仓库的完整 prompt，并包含范围、职责边界、端点与版本预期、测试、隐私约束以及 `do not commit/push`。

不知道需求归属时，可先把下面的通用分诊 prompt 复制到一个仓库；不要同时发送给两个任务：

```text
READ_ONLY
请只读分析以下需求的跨仓归属，不要修改文件、代码、API、schema、capabilities 或版本号：

[在此粘贴需求]

请将需求归类为且仅归类为 SFOS_ONLY、FC_ONLY 或 BOTH：
- SFOS_ONLY：UI、导航、Context Sources、Context LLM、Inference LLM、纯展示修改。
- FC_ONLY：财务实体、确定性计算、持久化、CSV、undo、通用财务 API。
- BOTH：SFOS 需要新增或修改 FC contract。

请说明归类依据、两个仓库的职责边界、预期端点与兼容版本、所需测试和隐私约束。
如果是 BOTH，请坚持 FC first：先实现并测试 FC、确定兼容 API 版本，再适配 SFOS；同时生成一份可直接发送给另一仓库的完整 prompt。
不得创建本地替代实现；不要读取真实财务数据、SQLite、导入导出文件或环境变量；do not commit/push。
```

发给 SFOS Codex 的标准 prompt：

```text
IMPLEMENT_APPROVED
请在 Soren-Finance-App 适配 Finance Core [版本] 的 [端点/能力]。
先读取 Finance Core 的 /api/v1/health 与 OpenAPI 契约，仅通过 HTTP Client 对接，不读取 FC 源码或 SQLite。
保持 Dashboard 只读，不在 SFOS 复制确定性财务规则。
补充契约测试、typecheck、build 和 README；不要修改 Finance-Core，不要 commit/push。
完成后输出 Cross-repo impact 区块。
```

## 隐私与 Git

- `.local-data`、SQLite/WAL/SHM、导入导出、环境文件、日志、私有媒体与备份均被忽略。
- 不得提交或输出真实财务记录、数据库路径、请求体、SQL 参数、密钥或凭证。
- FC 是唯一可写其财务数据库的进程。
- 不自动 commit 或 push；FC 与 SFOS 分别获得确认。

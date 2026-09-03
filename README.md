# Finance Core - v3.0.0

Finance Core（FC）是可复用、本地优先的个人财务领域与数据服务。它可以独立展示，也可以被 SFOS 等界面通过版本化 HTTP API 调用。

FC 不依赖 SFOS、Context Sources、OpenAI、Ollama 或任何 LLM。

## 能力与边界

```text
SFOS adapter / independent FC app
        │
        ▼
FastAPI /api/v3/workspaces/{workspaceId}
        │
deterministic domain + application operations
        │
Workspace resolver + scoped token
        │
Registry SQLite + one ledger SQLite per Vault
```

FC 拥有：

- `JournalEntry + Posting[]` 完整交易聚合、draft/validate/post/reversal
- Decimal string、Commodity Registry、类型化账户、显式 FX 估值
- 显式 lot acquisition/disposal 与只读派生 Holdings
- Recurring posting templates 与到期 draft 生成命令
- Living accounts、balance snapshots 与 monthly plans
- Dashboard metrics、T-account、financial statements、reconciliation
- JSON/CSV import/export
- 10 分钟、单次使用、后续写入会使旧 token 失效的 operation-level undo
- 一个本地 User 可拥有多个 personal/sandbox Workspace
- 每个 Vault 独立 SQLite、backup、undo 与访问授权
- 可恢复的 Workspace 隔离删除与 scoped API token

FC 不提供模型分析、投资建议、交易、支付、银行/券商连接或实时行情。

## 安装与运行

要求 Node.js、npm、Python 3.12 与 `uv`。

```powershell
cd <path-to-Finance-Core>
npm.cmd install --offline
uv sync --project backend --cache-dir .tmp/uv-cache
```

先从 `.env.example` 设置一个长随机 `FINANCE_CORE_ADMIN_TOKEN`。可选设置 `FINANCE_CORE_DATA_ROOT`；不得把真实值提交到 Git。

启动 API 与独立完整功能 FC UI：

```powershell
npm.cmd run dev
```

- FC UI：`http://127.0.0.1:5174`（通用、个人可用、与 SFOS 完全解耦）
- API：`http://127.0.0.1:8788`
- OpenAPI：`http://127.0.0.1:8788/docs`

也可只启动 API：

```powershell
npm.cmd run dev:api
```

## API v3

健康检查：`GET /api/v3/health`。v3 仅注册 `/api/v3`；旧 `/api/v1`、`/api/v2` 返回 404。

控制层：

- `POST/DELETE /api/v3/session`
- `GET /api/v3/me`
- `GET/POST /api/v3/workspaces`
- `PATCH/DELETE /api/v3/workspaces/{workspaceId}`
- `GET/POST /api/v3/access-tokens`
- `POST /api/v3/access-tokens/{tokenId}/revoke`
- `GET /api/v3/undo/latest?workspaceId=...`、`POST /api/v3/undo`

所有账本资源都位于 `/api/v3/workspaces/{workspaceId}/...`。一个请求只能访问一个 Vault；SFOS 可并发调用多个 Workspace，但必须保持结果分组，FC 不跨 Vault 合并数据。

普通可逆 C/U/D、导入、batch、余额记录和 backup restore 返回 `operationId`、`undoToken`、`expiresAt`、`workspaceId` 与 `operationType`。已过账事实不可删除，post/reversal 只能通过 linked reversal 更正；token revoke 和永久清除不可 undo。

`DELETE /api/v3/workspaces/{workspaceId}` 会 checkpoint 和校验 SQLite 后，把明确文件集移入 30 天可恢复隔离区，不执行递归或自动永久删除。

## 历史 API v2（3.0.0 不再注册）

下面仅保留迁移语义说明；端点在 FC 3.0.0 已停止注册。

健康与兼容性：`GET /api/v2/health`

主数据：

- `/api/v2/commodities`
- `/api/v2/accounts`
- `/api/v2/price-quotes`

完整交易生命周期：

- `/api/v2/journal-entry-drafts`
- `POST /api/v2/journal-entry-drafts/{id}/validate`
- `POST /api/v2/journal-entry-drafts/{id}/post`
- `/api/v2/journal-entries`（只读；posted entry 不允许 PATCH/DELETE）
- `POST /api/v2/journal-entries/{id}/reverse`

派生读模型与其他确定性功能：

- `/api/v2/dashboard`、`/t-accounts`、`/financial-statements`、`/cash-flow`、`/reconciliation`
- `/api/v2/holdings`（open lots 派生，只读）
- `/api/v2/living-accounts`、`/living-snapshots`、`/monthly-plans`、`/world`
- `/api/v2/recurring-entry-rules` 与 `POST /generate-due`（只生成 draft）
- `/api/v2/import/drafts`、`/api/v2/import/drafts.csv`
- `/api/v2/export`、`/api/v2/export/journal-entries.csv`
- `/api/v2/backup` 与 `/api/v2/backup/restore`（schema/hash 校验且只允许空 v2 ledger）
- `/api/v2/undo`（10 分钟单次 undo；post/reversal 会使旧 token 失效）

金额、余额、数量、成本、价格和汇率在公共契约中均为 canonical decimal string。Python 使用 `Decimal`；SQLite 保存规范字符串。Commodity `scale` 决定 units/金额精度，计算采用 `ROUND_HALF_EVEN`。跨商品 posting 必须显式提供 `valuationRate` 与 `rateType`，并在 entry 的 `balancingCommodityCode` 下精确平衡。

资产处置必须显式指定 lot allocations。FC 不自动选择 FIFO/LIFO，也不替用户决定税务策略。行情仅来自显式 `PriceQuote`；FC 不连接外部行情服务。

## 历史 API v1（3.0.0 不再注册）

v1 的历史读取语义仅供理解旧数据库；FC 3.0.0 不再提供 HTTP v1 端点。

旧资源仅保留 GET/export，以便人工迁移与审计：

- `/api/v1/transactions`
- `/api/v1/holdings`
- `/api/v1/recurring-rules`
- `/api/v1/living-accounts`
- `/api/v1/living-snapshots`
- `/api/v1/monthly-plans`
- `/api/v1/account-options`

旧查询：

- `GET /api/v1/dashboard`
- `GET /api/v1/t-accounts`
- `GET /api/v1/financial-statements`
- `GET /api/v1/reconciliation`
- `GET /api/v1/export`
- `GET /api/v1/export/{transactions|holdings}.csv`

兼容规则：Patch 只做兼容修复；Minor 可增加端点或可选字段；删除、重命名、改变 requiredness 或语义必须升级 Major。FC 2 客户端范围为 `>=2.0.0 <3.0.0`。

## 数据迁移

先只读检查源库，再执行 dry-run：

```powershell
uv run --project backend python -m finance_core.maintenance inspect --source '<source-db>'
uv run --project backend python -m finance_core.maintenance migrate --source '<source-db>' --data-root '<fc-v3-data-root>' --display-name '<vault-name>' --kind personal --dry-run
```

真实迁移必须先停止源库写入进程、创建备份并获得 `REAL_DATA_MIGRATION_APPROVED`：

```powershell
uv run --project backend python -m finance_core.maintenance migrate --source '<source-db>' --data-root '<fc-v3-data-root>' --display-name '<vault-name>' --kind personal
```

迁移工具遵守以下边界：

- 源 DB 始终以 read-only 模式检查，复制到新建 Vault，不移动、不覆盖也不删除源文件；
- 复制前后运行 `PRAGMA integrity_check`、`PRAGMA foreign_key_check`、表行数和 SHA-256 检查；
- 每次创建独立 Workspace/Vault，不把多个用户或 Vault 合并进同一 SQLite；
- 删除源 DB 是另一项显式维护操作：先 checkpoint 与校验，再将明确的 SQLite/WAL/SHM 文件移入 30 天可恢复隔离区，并生成私有 recovery file；不会递归删除或自动永久清除。

## 测试与构建

```powershell
npm.cmd test
npm.cmd run build
```

当前测试覆盖 v3 session、Workspace/Vault 隔离、scoped token、可恢复删除、undo、aggregate lifecycle、Decimal/scale、FX、显式 lot、reversal、派生持仓与报表、living world、JSON/CSV draft import、周期 draft、hash backup restore 和安全迁移。全部使用合成数据与临时 SQLite。

## 独立 FC UI 边界

- FC UI 只调用 `/api/v3` HTTP API，不访问 SQLite、repository 或 backend 内部对象。
- UI 不导入 SFOS 类型、组件、CSS、客户端或配置；SFOS 也不依赖 FC UI。
- 提供 Commodity/Account/Price、draft editor、split posting、FX、lot、validation、post、reversal、派生报表、生活账户、计划、周期、import/export、backup 和 undo 的交互。
- 一键示例只允许在空 sandbox Vault 装载通用合成数据，personal Vault 不显示造数入口。
- 没有 active Vault 时，UI 强制显示创建数据空间窗口。

API 调用、PowerShell 环境变量、认证、启动链路、loading 并发问题与源码局部解构见 [`docs/md/01-fc-v3-api-env-loading.md`](docs/md/01-fc-v3-api-env-loading.md)。

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
请在 Soren-Finance-App 适配 Finance Core 3.0.0 的 Workspace-scoped /api/v3 aggregate ledger。
先读取 Finance Core 的 /api/v3/health 与 OpenAPI 契约，仅通过 backend HTTP Client 对接，不读取 FC 源码或 SQLite。Bearer token 只从 SFOS backend 环境变量读取，不得发送到浏览器。
使用 JournalEntryDraft -> validate -> human confirm -> post；posted 更正只调用 reversal。Decimal string 不得转为 JS number 后回写。保持 Dashboard/Holdings 只读，不在 SFOS 复制确定性财务规则或依赖 FC Demo。
补充契约测试、typecheck、build 和 README；不要修改 Finance-Core，不要 commit/push。
完成后输出 Cross-repo impact 区块。
```

## 隐私与 Git

- `.local-data`、SQLite/WAL/SHM、隔离区、导入导出、环境文件、日志、私有媒体与备份均被忽略。
- 不得提交或输出真实财务记录、数据库路径、请求体、SQL 参数、密钥或凭证。
- FC 是唯一可写其财务数据库的进程。
- 不自动 commit 或 push；FC 与 SFOS 分别获得确认。

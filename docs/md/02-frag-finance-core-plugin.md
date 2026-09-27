# FRAG-harness 的可选 Finance Core 插件（v1.0.0）

Finance Core 3.1.1 可独立启动和使用。FRAG-harness 可安装单独的只读插件，通过 FC 的公开 HTTP API 显示 Dashboard 并读取人工指定的少量 Journal 记录。FC 的 domain、application、API、SQLite 与独立 UI 都不依赖 FRAG。所有 Journal 修改须打开 FC 自身 UI，由 FC 登录和执行。

## 兼容性与交付文件

| 项目 | 版本或位置 |
| --- | --- |
| FRAG plugin protocol | 1 |
| FRAG host | 1.0.0 |
| FC API | 3.1.1 |
| 插件语义版本 | 1.0.0 |
| 归档 | `docs/release/finance-core-frag-plugin-v1.0.0.zip` |
| 源文件 | `plugins/finance-core/manifest.json`、`adapter.py`、`ui.js` |

归档根目录恰好包含 `manifest.json`、`adapter.py`、`ui.js`。`manifest.json` 将两个代码文件的 SHA-256 固定在 `files` 中。归档自身 SHA-256 由 `python tools/build_frag_plugin.py --check` 输出；安装时必须使用这个值。`.gitignore` 对此官方 ZIP 有明确例外，可由用户决定是否提交；本任务不提交或推送。

## 后端配置

FRAG 后端环境中配置以下变量。只在 FC 自身 UI 创建一个限制到目标 Workspace、且仅含 `ledger:read` scope 的 access token；不得把它放进浏览器代码、URL、日志、截图或 Git。

```text
FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788
FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174
FINANCE_CORE_PLUGIN_READ_TOKEN=<backend-only scoped read token>
FINANCE_CORE_PLUGIN_RECORDS_JSON={"<workspace-uuid>":["entry:<entry-id>","draft:<draft-id>"]}
```

`FINANCE_CORE_PLUGIN_RECORDS_JSON` 是由本机用户明确选择的候选列表，所有 Workspace 合计最多 10 个不同记录 ID。插件不会扫描完整 Journal 列表，也不从 FC Registry 或 Vault SQLite 读取。未配置候选时，`GET /scopes` 返回空列表；未配置 token 或 FC 不可用时返回不可用状态。API 与 UI 地址只接受本机 loopback HTTP 地址。

候选 ID 的 `entry:` 与 `draft:` 前缀分别指向 FC 3.1.1 的单条已过账交易和草稿读端点。`GET /scopes` 只展示 token 可访问、状态为 active 的 Workspace 及配置的记录。`read_evidence(workspace_id, record_ids)` 必须收到同一 Workspace 下已配置的 1 到 10 个、互不重复的 ID；它逐条读取并返回相同顺序的 `recordId`、`label`、`text`、`revision`。`revision` 是 FC 返回记录的规范 JSON 的 SHA-256。每条 `text` 最多 8,000 字符，包含日期、描述、状态和最多 200 条 posting 的有限字段。不要把该摘要当作完整 FC 账本导出。

## FC HTTP 读契约

- `GET /api/v3/health`：验证 `service=finance-core`、`status=ok`、`apiVersion=3.1.1`。
- `GET /api/v3/workspaces`：只读验证 token 可访问的 active Workspace。
- `GET /api/v3/workspaces/{workspaceId}/dashboard`：读 FC 计算的原始 Dashboard 值；金额保留 Decimal string。
- `GET /api/v3/workspaces/{workspaceId}/journal-entries/{entryId}` 与 `GET /api/v3/workspaces/{workspaceId}/journal-entry-drafts/{draftId}`：只读获取配置的所选记录。

FC API 无需新增端点或改版本。插件路由只提供 `GET /api/plugins/finance-core/scopes` 与 `GET /api/plugins/finance-core/dashboard?workspaceId=...`；前端只调用 FRAG 同源插件路由。后端按 Workspace 与记录白名单检查访问，拒绝跨 Workspace、重复、超过 10 个或无效记录 ID。FC 版本不兼容返回 409；FC 未配置、超时或不可用返回 503。响应和错误不包含 token、数据库路径或私有请求体。

## 本地安装与验证

先从本仓库核对归档和 SHA-256：

```powershell
python tools/build_frag_plugin.py --check
npm.cmd test -- --basetemp .tmp/<new-unique-pytest-dir>
npm.cmd run check:release
npm.cmd run check:versions
```

之后由 FRAG 仓库自己的安装流程以 `-ArchivePath` 和核对过的 `-ExpectedSha256` 安装，并重启 FRAG。安装、启用和禁用状态由 FRAG host 管理；本 FC 仓库不写 FRAG 文件。FRAG 的 `current.json` 必须指向插件 `1.0.0`，并明确 `enabled: true`。只有 FRAG 可以把插件路由和前端 bundle 加载进其运行时。

历史 SFOS 迁移、3.0.0 Horizon 和 v1/v2 API 说明保留原始历史语义。此文档只描述当前可选插件，不改变 FC 的确定性计算、认证或数据库写入者。

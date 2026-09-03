# Finance Core v3.0.0 Project Horizon

生成日期：2026-09-03

## 1. 文档定位

本文件描述 Finance Core 3.0.0 已经具备的边界，以及从当前架构出发可以继续扩展的方向。Horizon 是技术视野，不是发布日期承诺；没有进入当前代码、OpenAPI 和测试的能力都必须标记为候选。

## 2. 当前已实现能力

- 一个本地 Owner User 可以创建多个 `personal` 或 `sandbox` Workspace。
- 每个 Workspace/Vault 拥有独立 SQLite、WAL、undo、backup 和显式 `/api/v3/workspaces/{workspaceId}` 路径。
- SFOS 等客户端使用只在 backend 保存的 scoped Bearer token，可被限制到指定 Workspace 和 `ledger:read` / `ledger:write`。
- Commodity Registry、类型化账户、PriceQuote、JournalEntryDraft、validate、post、linked reversal、显式 FX、显式 lot、持仓与确定性报表继续由 FC 负责。
- 普通可逆 C/U/D、导入、batch、余额记录与 backup restore 返回 operation-level undo；posted JournalEntry 仍保持不可变。
- Vault 删除会先 checkpoint 与校验，再进入 30 天可恢复隔离区；不会递归删除目录或自动永久清除。
- FC UI 支持零 Vault 创建、Vault 切换、personal/sandbox 边界、纵向交易工作流和局部 loading 状态。

## 3. 当前明确不具备

- 不提供公网生产部署、TLS 终止、注册、密码登录、MFA 或完整多用户 ACL。
- 不提供数据库静态加密或密钥轮换。
- 不连接银行、券商、支付、实时行情、OpenAI、Ollama 或任何 LLM。
- 不跨 Vault 混合余额、持仓、报表或财务行。
- 不自动选择 FIFO/LIFO，不替用户做税务判断、投资判断或最终财务判断。
- 不允许通过 undo 删除 post/reversal 形成的不可变账本事实。

## 4. 近期 Horizon - 可通过 v3.x 增量扩展

### H1.1 可运维性与恢复演练（FC_ONLY）

- 增加可视化 backup catalog、恢复演练和只读灾难恢复报告。
- 增加 Registry 与各 Vault 的健康矩阵、容量趋势和 WAL checkpoint 可见性。
- 为 quarantine 增加不暴露路径和私人行的管理视图。

### H1.2 财务录入体验（FC_ONLY）

- 增加可复用 JournalEntry 模板、键盘优先录入和字段级错误定位。
- 增加账户停用影响预览、批量草稿校验和导入 dry-run 报告。
- 增加显式对账工作台，但不自动改写账本事实。

### H1.3 SFOS 适配体验（BOTH）

- 在 SFOS backend 中提供 Workspace allowlist、单选/多选和部分失败分组响应。
- 增加 FC contract compatibility 页面，明确 service/API/schema 版本。
- token 继续只存在于 SFOS backend，浏览器只看到脱敏 Workspace 元数据。

## 5. 下一 Major Horizon - 需要新的合同或安全模型

### H2.1 真正多用户与授权（BOTH）

- 引入独立 authentication provider、User/Group、Workspace membership 和 least-privilege ACL。
- 将当前 local Owner session 迁移为可审计的主体，不把 Workspace 当作登录 User。
- 需要新的 major API、权限迁移工具、会话吊销和安全测试矩阵。

### H2.2 静态加密与密钥生命周期（FC_ONLY）

- 评估 SQLCipher 或等价方案，覆盖 Registry 与每个 Vault。
- 必须先设计密钥生成、备份、轮换、恢复、遗失和离线迁移流程。
- 加密不能替代操作系统权限、token scope、审计和备份验证。

### H2.3 可部署服务边界（BOTH）

- 在反向代理、TLS、Origin、CSRF、rate limit 和安全 header 完成前不得公开监听。
- 明确单机多 Vault 与多实例部署的一致性、锁、backup 和升级协议。
- 发布前需要威胁建模、渗透测试和真实恢复演练。

## 6. 长期研究 Horizon

### H3.1 数据连接器（BOTH）

- 银行或券商导入必须先进入 staging/draft，不得直接 post。
- 连接器需要来源指纹、去重、可撤销导入和人工确认。
- 第三方凭证必须位于 backend secret boundary，不进入 FC UI 或财务导出。

### H3.2 更丰富的确定性财务域（FC_ONLY）

- 多期间 closing、预算版本、责任中心、成本中心和更完整的财务报表。
- 税务 lot 报告只能提供可追溯计算，不自动决定税务策略。
- 所有新增金额合同继续使用 canonical Decimal string。

### H3.3 受控智能辅助（SFOS_ONLY 或 BOTH）

- LLM 只能在 SFOS 的显式 Context/Inference 边界内工作，不能成为 FC 确定性计算或 SQLite writer。
- 若未来需要 FC 提供 evidence contract，必须使用新的版本化只读合同和合成测试。
- Human 始终保留最终财务与投资判断。

## 7. 扩展约束与 Anti-goals

- FC 必须保持独立可运行，不依赖 SFOS 才能解释其财务语义。
- Domain 不导入 FastAPI、SQLite、React、HTTP client 或 SFOS 类型。
- 不为某一个 SFOS 页面复制一套只适用于该页面的财务规则。
- 不把物理 DB 路径、token、请求体、SQL、真实记录或 recovery secret 写入日志、PDF 或 Git。
- 不把 Horizon 候选写进 capability 列表，除非代码、合同和测试已经落地。

## 8. 版本与证据

- Service version：3.0.0
- API version：3.0.0
- Ledger schema version：2
- Registry schema version：1
- 验证基线：backend tests、OpenAPI scoped contract、production UI build、版本同步检查、PDF render/text QA。
- 内容依据：当前代码、OpenAPI、synthetic tests、README 与 AGENTS.md；不使用真实财务数据。


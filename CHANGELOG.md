# 更新日志

## v1.0.0 (2026-08-11)

初始版本。本项目由 [Chris95743/astrbot_plugin_gemini_search](https://github.com/Chris95743/astrbot_plugin_gemini_search) v1.3.0 重构改名而来，适配新版 AstrBot（v4.26+）。

### 新增
- `/gemini <问题>` 指令：不经过 LLM 函数工具调用，直接触发联网搜索并回复结果。
- 内置双检索提示词：`/gemini` 指令版先给一句话结论再分条要点附来源，LLM 工具版侧重多角度检索、优先权威来源、要点附事实依据；两者均要求纯文本输出（适配 QQ 等不渲染 Markdown 的渠道）。
- `custom_search_prompt` 配置：检索提示词可在 WebUI 中自定义（带编辑器），填写后覆盖两种内置提示词。
- Markdown 兜底剥离：无论模型是否遵守提示词，搜索结果返回前都会去除行首标题/引用/列表前缀与行内链接/粗体/行内代码标记，有序编号保留。
- 工具模式结果包装：以 `搜索结果:` 开头、结尾附 `[提示: 请使用纯文本格式回复用户，不要使用 Markdown 格式]`——明确标示调用成功（避免主模型受会话历史中失败记录影响误判），并引导主模型以纯文本回复用户。
- `enable_fetch` 开关：`web_fetch_gemini` 网页抓取工具可在配置中一键禁用（禁用时自动从 LLM 工具表摘除）。
- 多 API Key 按顺序轮询分摊负载；client 按 `api_key + api_base_url` 组合键缓存，修改 base_url 后不会复用旧连接。

### 变更
- 项目改名为 `astrbot_plugin_gemini_web_search`，版本从 v1.0.0 重新起算。
- LLM 函数工具命名为 `web_search_gemini`、`web_fetch_gemini`：符合 AstrBot 内置搜索工具 `web_search_<服务名>` 的命名惯例，避免裸名与其他插件同名工具互相覆盖，也不使用 `gemini_` 前缀以免与 Gemini 后端内部函数命名混淆。
- 配置结构为分组形式：`direct_settings`（API 连接）、`search_settings`（提示词）、`tool_settings`（抓取工具）。与原项目平铺配置不兼容，需重新填写。
- 适配新版 AstrBot：构造函数调用 `super().__init__(context)`；`/gemini` 指令回复后显式禁止本事件的默认 LLM 回复。
- 默认模型由 `gemini-2.0-flash` 更新为 `gemini-2.5-flash`。
- requirements.txt 精简为仅 `beautifulsoup4`（`google-genai`、`httpx` 已是 AstrBot 本体依赖）。

### 移除
- 移除原项目的 `webshot_analyze`、`webshot_send` 两个截图工具及其全部配套逻辑与配置项：强依赖不稳定的免费第三方截图服务，且会向第三方泄露访问的 URL。
- 移除 `random_api_key_selection` 随机选 Key 开关（固定顺序轮询，负载更均匀）。

## 更早历史
- 见原项目 [astrbot_plugin_gemini_search](https://github.com/Chris95743/astrbot_plugin_gemini_search) 提交历史。

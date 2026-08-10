
<div align="center">

# astrbot_plugin_gemini_web_search

_✨ [AstrBot](https://github.com/AstrBotDevs/AstrBot) 基于 Gemini 原生 Google Search 工具的联网搜索插件 ✨_

[![License](https://img.shields.io/badge/License-AGPL--3.0-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.26%2B-orange.svg)](https://github.com/AstrBotDevs/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-monbed-blue)](https://github.com/monbed)

</div>

通过 Gemini 原生 `GoogleSearch` 工具进行实时联网检索，结果提炼为"要点摘要 + 引用来源（标题+URL）"。支持 `/gemini` 指令直接搜索，也作为 LLM 函数工具供主模型在对话中自动调用；另附可开关的 `web_fetch_gemini` 网页纯文本抓取工具。

## 功能特性

- **`/gemini <问题>` 指令**：直接触发联网搜索并回复结果，无需经过 LLM 工具调用
- **原生 Google Search 工具**：无需自建爬虫，检索能力由 Gemini 托管
- **结果结构化**：要点式摘要 + 参考来源列表（标题 + URL），提示词可在配置中自定义
- **多 Key 轮询**：多个 API Key 按顺序轮询分摊负载；`api_base_url` 可自定义（兼容官方地址与 Gemini 原生格式的反代地址）
- **`web_fetch_gemini` 网页抓取**：抓取网页纯文本（剔除 script/style）供模型阅读，可在配置中一键关闭

## 入口一览

| 入口 | 说明 |
|---|---|
| `/gemini <问题>` | 指令直接联网搜索 |
| `web_search_gemini(query)` | LLM 函数工具，主模型需要实时信息时自动调用 |
| `web_fetch_gemini(url)` | LLM 函数工具，抓取网页纯文本（可配置关闭） |

## 安装

### 方式一：插件市场安装（推荐）
1. 在 AstrBot 插件市场搜索 `astrbot_plugin_gemini_web_search`
2. 点击安装，等待安装完成后重启 AstrBot

### 方式二：手动克隆安装
```bash
cd /AstrBot/data/plugins
git clone https://github.com/monbed/astrbot_plugin_gemini_web_search
# 重启 AstrBot
```

## 快速开始

1. 打开 Dashboard → 插件 → `astrbot_plugin_gemini_web_search` → 配置
2. 在『API 设置』中填写至少一个 Gemini API Key
3. 会话中发送 `/gemini 今天有什么科技新闻`，或直接向模型提问需要实时信息的问题

## 配置说明

### direct_settings —— API 设置

| 配置项 | 说明 | 默认 |
|---|---|---|
| `api_key` | Gemini API Key 列表，多 Key 按顺序轮询 | `[]` |
| `api_base_url` | API 基础地址，可填官方地址或兼容 Gemini 原生格式的反代地址 | 官方地址 |
| `model` | 搜索模型 | `gemini-2.5-flash` |

### search_settings —— 搜索设置

| 配置项 | 说明 |
|---|---|
| `custom_search_prompt` | 自定义检索提示词。留空使用内置双提示词：`/gemini` 指令版侧重"先结论后要点"，LLM 工具版侧重多角度检索与来源依据；两者均要求纯文本输出（适配 QQ 等不渲染 Markdown 的渠道，也避免部分模型后端对 Markdown 工具结果处理不稳）。填写后两种模式均以此为准，问题自动追加在提示词之后。无论提示词如何，结果返回前都会兜底剥离 Markdown 标记 |

### tool_settings —— 工具设置

| 配置项 | 说明 | 默认 |
|---|---|---|
| `enable_fetch` | 是否启用 `web_fetch_gemini` 网页抓取工具 | `true` |
| `fetch_timeout_seconds` | 网络请求超时（秒） | `20` |
| `fetch_user_agent` | 抓取网页 UA | `Mozilla/5.0 AstrBot` |
| `fetch_max_chars` | 最大返回字符数 | `20000` |

## 工作原理

1. 插件注册 `/gemini` 指令与 `web_search_gemini`、`web_fetch_gemini` 函数工具
2. 触发搜索时，按配置的 API Key（轮询）与 base_url 建立 google-genai 异步客户端
3. 调用 Gemini 并启用原生 `GoogleSearch` 工具进行检索
4. 模型返回要点摘要与来源列表；指令模式直接回复用户，工具模式作为工具结果注入会话供主模型综合作答

## 常见问题

**Q1: 一定要用官方域名吗？**
不一定。`api_base_url` 可填反代地址，只需兼容 `google-genai` SDK 的 API 约定。

**Q2: 工具没有被主模型调用？**
确保当前会话使用的模型/Provider 支持函数工具，且插件已加载。也可直接用 `/gemini` 指令。

**Q3: 为什么搜索必须走 Gemini？**
Google Search 是 Gemini 的厂商专属原生工具，须通过 google-genai 客户端启用，其他模型无法使用。

## 依赖

- `beautifulsoup4>=4.12.0`（已在插件 `requirements.txt` 中声明，用于网页文本提取）
- `google-genai`、`httpx` 为 AstrBot 本体自带依赖，无需额外安装

## 版本与兼容

- 默认模型：`gemini-2.5-flash`
- AstrBot：v4.16+（推荐 v4.26+）
- 更新历史见 [CHANGELOG.md](CHANGELOG.md)

## 隐私与合规

- 搜索查询会交给 Google 的生成式 AI 服务处理，请勿输入敏感/个人隐私信息
- 遵循目标站点的访问与使用条款，引用来源请规范标注

## 致谢

- 本插件基于 [Chris95743/astrbot_plugin_gemini_search](https://github.com/Chris95743/astrbot_plugin_gemini_search) 重构而来，感谢原作者 Chris 的工作
- 指令入口与配置结构借鉴了 [piexian/astrbot_plugin_grok_web_search](https://github.com/piexian/astrbot_plugin_grok_web_search)

---

<div align="center">

如果觉得有用，请给个 ⭐ Star 支持一下！

</div>

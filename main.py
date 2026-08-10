from typing import Optional
import re

import astrbot.api.star as star
from astrbot.api import llm_tool, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr

# Google GenAI SDK
from google import genai
from google.genai import types

# HTTP & HTML parsing
try:
	import httpx
except Exception:  # pragma: no cover - 延迟导入失败时给出友好提示
	httpx = None

try:
	from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
	BeautifulSoup = None

PLUGIN_NAME = "astrbot_plugin_gemini_web_search"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_API_BASE = "https://generativelanguage.googleapis.com"

# 工具模式提示词：结果作为 tool 消息交给主模型综合。
# 与指令模式一样要求纯文本——部分模型后端的函数调用桥接对含 Markdown 的工具结果处理不稳
TOOL_SEARCH_PROMPT = (
	"你是联网检索助手。请使用 Google Search 工具检索下述问题。"
	"检索策略：先从多个角度广泛检索，再深入最相关的结果；"
	"优先采用权威来源（官方文档、维基百科、学术论文、可靠媒体）。\n"
	"输出要求：\n"
	"1) 条目式关键要点摘要，每条结论须有事实依据；\n"
	"2) 参考来源列表（标题 + URL），按相关性排序。\n"
	"重要：使用纯文本输出，不要使用任何 Markdown 标记"
	"（不要出现 **、#、`、- 等符号，列举用 1. 2. 3. 编号）。\n"
	"避免冗长描述，直接给出结论与来源。"
)

# 指令模式提示词：结果直接发给用户，QQ 等渠道不渲染 Markdown，要求纯文本
CMD_SEARCH_PROMPT = (
	"你是联网检索助手。请使用 Google Search 工具检索下述问题，"
	"优先采用权威来源（官方文档、维基百科、学术论文、可靠媒体）。\n"
	"用中文回答：先给出一句话直接结论，再分条列出关键要点，"
	"最后附参考来源（标题 + URL）。\n"
	"重要：使用纯文本输出，不要使用任何 Markdown 标记"
	"（不要出现 **、#、`、- 等符号，列举用 1. 2. 3. 编号）；"
	"专有名词保留原文；内容简洁、结论可溯源。"
)

# Markdown 轻量降级为纯文本的行首/行内标记
_RE_MD_HEADING = re.compile(r"^#{1,6}\s+")
_RE_MD_QUOTE = re.compile(r"^>\s?")
_RE_MD_BULLET = re.compile(r"^[\-*+]\s+")
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RE_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_MD_CODE = re.compile(r"`([^`]+)`")


class Main(star.Star):
	"""
	使用 Gemini + Google Search 原生工具进行联网检索。

	通过插件配置的 api_key + api_base_url 直连 Gemini API
	（兼容官方地址与 Gemini 原生格式的反代地址），
	多个 API Key 按顺序轮询分摊负载。
	"""

	def __init__(self, context: star.Context, config=None) -> None:
		super().__init__(context)
		# AstrBot 会根据 _conf_schema.json 构造 config（AstrBotConfig），此处按 dict 访问
		self.config = config or {}
		self._rr_key_index = 0  # API Key 轮询下标
		self._clients: dict[str, object] = {}  # client 缓存（键为 api_key@base_url）

	def _cfg(self, section: str, key: str, default=None):
		"""读取分组配置（object 节）中的一项，节不存在或不是 dict 时返回默认值。"""
		sec = self.config.get(section)
		if isinstance(sec, dict) and key in sec:
			return sec[key]
		return default

	def _fetch_enabled(self) -> bool:
		return bool(self._cfg("tool_settings", "enable_fetch", True))

	async def initialize(self):
		self.context.activate_llm_tool("web_search_gemini")
		if self._fetch_enabled():
			self.context.activate_llm_tool("web_fetch_gemini")
		else:
			self.context.deactivate_llm_tool("web_fetch_gemini")
			logger.info(f"[{PLUGIN_NAME}] web_fetch_gemini 工具已按配置禁用")

		keys = self._cfg("direct_settings", "api_key", []) or []
		if keys:
			logger.info(f"[{PLUGIN_NAME}] 已配置 {len(keys)} 个 API Key")
		else:
			logger.warning(f"[{PLUGIN_NAME}] 尚未配置 api_key，请在插件设置中填写。")

	@filter.command("gemini", desc="Gemini 联网搜索，用法：/gemini <问题>")
	async def gemini_cmd(self, event: AstrMessageEvent, query: GreedyStr):
		"""直接触发 Gemini 联网搜索并回复结果。"""
		query = str(query).strip()
		if not query:
			yield event.plain_result("用法：/gemini <要搜索的问题>")
			return
		text = await self._do_search(query, for_command=True)
		event.should_call_llm(True)  # 禁止本事件再触发默认 LLM 回复
		yield event.plain_result(text)

	@llm_tool("web_search_gemini")
	async def web_search_gemini(self, event: AstrMessageEvent, query: str) -> str:
		"""这是一个“联网搜索”的函数工具（工具名：web_search_gemini）。当需要获取互联网上的实时/最新信息时，你必须调用本工具进行搜索。

		Args:
			query(string): 简要说明用户希望检索的查询内容

		Returns:
			str: 要点摘要与引用来源，作为 tool 消息注入上下文
		"""
		return await self._do_search(query)

	async def _do_search(self, query: str, for_command: bool = False) -> str:
		"""执行一次 Gemini + Google Search 检索，返回结果文本（失败时返回错误说明）。

		for_command=True 时使用指令模式提示词（纯文本，直接发给用户）；
		否则使用工具模式提示词（结构化，交给主模型综合）。
		配置了 custom_search_prompt 时两种模式均以其为准。
		"""
		try:
			client, model = self._resolve_gemini()
		except Exception as e:
			logger.error(f"[{PLUGIN_NAME}] 获取 Gemini 客户端失败: {e}")
			return str(e)

		# 启用原生 Google Search 工具
		config = types.GenerateContentConfig(
			tools=[types.Tool(google_search=types.GoogleSearch())],
			temperature=0.2,
		)

		custom_prompt = str(self._cfg("search_settings", "custom_search_prompt", "") or "").strip()
		search_prompt = custom_prompt or (CMD_SEARCH_PROMPT if for_command else TOOL_SEARCH_PROMPT)
		prompt = f"{search_prompt}\n问题：{query}"

		try:
			resp = await client.models.generate_content(
				model=model,
				contents=prompt,
				config=config,
			)
			text = getattr(resp, "text", None) or self._extract_text(resp)
			if not text:
				return "未从检索中获得可用文本结果。"
			# 兜底剥离 Markdown 标记，保证两种模式的输出均为纯文本
			plain = self._markdown_to_plain(text.strip())
			if for_command:
				return plain
			# 工具模式：包装为明确的结果格式，并附纯文本回复提示，
			# 防止主模型受历史失败记录影响误判调用失败或用 Markdown 回复
			return (
				f"搜索结果:\n{plain}\n\n"
				"[提示: 请使用纯文本格式回复用户，不要使用 Markdown 格式]"
			)
		except Exception as e:
			logger.error(f"[{PLUGIN_NAME}] 检索调用失败: {e}")
			return f"检索失败：{e}"

	@llm_tool("web_fetch_gemini")
	async def web_fetch_gemini(self, event: AstrMessageEvent, url: str) -> str:
		"""抓取网页文本内容（去标签纯文本）。

		Args:
			url(string): 需要抓取内容的网页 URL

		Returns:
			str: 提取的纯文本（可配置长度上限），失败时返回错误信息
		"""
		if not self._fetch_enabled():
			return "网页抓取工具已在插件配置中禁用。"
		if httpx is None:
			return "插件缺少依赖 httpx，请在该插件 requirements.txt 中安装后重启。"
		try:
			text = await self._fetch_page_text(url)
			if not text:
				return "未能从页面中提取到有效文本。"
			max_chars = int(self._cfg("tool_settings", "fetch_max_chars", 20000))
			return text[:max_chars]
		except Exception as e:
			logger.error(f"[{PLUGIN_NAME}] web_fetch_gemini 抓取失败: {e}")
			return f"抓取失败：{e}"

	# ---------------- Gemini 客户端解析 ----------------

	def _resolve_gemini(self):
		"""按配置解析出 (client, model)。未配置 api_key 时抛出带指引的异常。"""
		keys = self._cfg("direct_settings", "api_key", []) or []
		if not keys:
			raise RuntimeError("请先在插件配置中填写至少一个 Gemini API Key。")
		client = self._get_client(keys)
		model = self._cfg("direct_settings", "model", "") or DEFAULT_MODEL
		return client, model

	def _get_client(self, keys: list[str]):
		"""按顺序轮询 API Key，创建/复用异步 client。"""
		key = keys[self._rr_key_index % len(keys)]
		self._rr_key_index += 1

		api_base = (
			self._cfg("direct_settings", "api_base_url", "") or DEFAULT_API_BASE
		).rstrip("/")

		cache_key = f"{key}@{api_base}"
		if cache_key in self._clients:
			return self._clients[cache_key]

		http_options = types.HttpOptions(base_url=api_base)
		client = genai.Client(api_key=key, http_options=http_options).aio
		self._clients[cache_key] = client
		return client

	# ---------------- 网页抓取 ----------------

	async def _fetch_page_text(self, url: str) -> Optional[str]:
		"""抓取网页并提取纯文本。"""
		timeout = float(self._cfg("tool_settings", "fetch_timeout_seconds", 20))
		ua = str(self._cfg("tool_settings", "fetch_user_agent", "") or "Mozilla/5.0 AstrBot")
		async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": ua}, follow_redirects=True) as client:
			resp = await client.get(url)
			resp.raise_for_status()
			html = resp.text
			if BeautifulSoup is None:
				# 退化处理：简单去标签
				return html
			soup = BeautifulSoup(html, "html.parser")
			# 移除脚本与样式
			for tag in soup(["script", "style", "noscript"]):
				tag.decompose()
			text = soup.get_text("\n")
			# 简单压缩空行
			lines = [ln.strip() for ln in text.splitlines()]
			return "\n".join([ln for ln in lines if ln])

	@staticmethod
	def _markdown_to_plain(text: str) -> str:
		"""将 Markdown 轻量降级为纯文本：去除行首标题/引用/列表前缀与行内链接/粗体/行内代码标记。
		对无标记文本基本幂等。"""
		if not text:
			return text
		out = []
		for line in text.split("\n"):
			s = line
			for pat in (_RE_MD_HEADING, _RE_MD_QUOTE, _RE_MD_BULLET):
				s = pat.sub("", s, count=1)
			s = _RE_MD_LINK.sub(r"\1 (\2)", s)
			s = _RE_MD_BOLD.sub(r"\1", s)
			s = _RE_MD_CODE.sub(r"\1", s)
			out.append(s)
		return "\n".join(out)

	@staticmethod
	def _extract_text(resp) -> Optional[str]:
		"""兼容性提取：把 candidates/parts 文本拼起来。"""
		try:
			if not resp or not getattr(resp, "candidates", None):
				return None
			parts = []
			for c in resp.candidates:
				content = getattr(c, "content", None)
				if not content or not getattr(content, "parts", None):
					continue
				for p in content.parts:
					t = getattr(p, "text", None)
					if t:
						parts.append(t)
			return "\n".join(parts) if parts else None
		except Exception:
			return None

from astrbot.api.all import *
import time
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "影视搜索插件", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.pagination_cache = {}
        self.platform_type = context.platform  # 获取平台类型

    def _get_session_id(self, event):
        """跨平台用户会话标识获取"""
        try:
            # 微信开放平台专用字段
            if self.platform_type == "gewechat":
                return event.origin_user_id
            # 其他平台回退
            return event.get_sender_id()
        except AttributeError:
            return f"{hash(event)}-{time.time()}"

    # [保持其他方法不变，只修改涉及用户标识的部分]

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        if not self.api_url_vod:
            yield event.plain_result("⚠️ 普通视频服务未启用")
            return
        
        pages = await self._common_handler(event, self.api_url_vod, text)
        session_id = self._get_session_id(event)
        self.pagination_cache[session_id] = {
            "pages": pages,
            "timestamp": time.time()
        }
        
        yield event.plain_result(pages[0])
        if len(pages) > 1:
            yield event.plain_result(f"【分页提示】回复2-{len(pages)}查看后续内容（20秒内有效）")

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        if not self.api_url_18:
            yield event.plain_result("🔞成人内容服务未启用")
            return
        
        pages = await self._common_handler(event, self.api_url_18, text)
        session_id = self._get_session_id(event)
        self.pagination_cache[session_id] = {
            "pages": pages,
            "timestamp": time.time()
        }
        
        yield event.plain_result(pages[0])
        if len(pages) > 1:
            yield event.plain_result(f"【分页提示】回复2-{len(pages)}查看后续内容（20秒内有效）")

    @filter.regex(r"^\d+$")
    async def handle_pagination(self, event: AstrMessageEvent):
        session_id = self._get_session_id(event)
        cache = self.pagination_cache.get(session_id)
        
        if not cache or (time.time() - cache["timestamp"]) > 20:
            return
        
        try:
            page_num = int(event.message_str.strip())
        except ValueError:
            return
        
        pages = cache["pages"]
        if 1 < page_num <= len(pages):
            yield event.plain_result(pages[page_num - 1])
        elif page_num == 1:
            yield event.plain_result("已经是第一页啦")
        else:
            yield event.plain_result(f"无效页码，请输入2-{len(pages)}之间的数字")

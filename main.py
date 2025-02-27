from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import asyncio

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "")
        self.api_url_18 = config.get("api_url_18", "")
        self.current_results = {}
        self.current_pages = {}

    async def _common_handler(self, event, api_url, keyword):
        """通用请求处理核心逻辑"""
        if not api_url:
            yield event.plain_result("?? 服务未正确配置，请联系管理员")
            return

        encoded_keyword = urllib.parse.quote(keyword)
        query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(query_url, timeout=15) as response:
                    if response.status != 200:
                        yield event.plain_result(f"?? 服务暂时不可用（状态码 {response.status}）")
                        return

                    html_content = await response.text()
                    parsed_result = self._parse_html(html_content)

                    if not parsed_result:
                        yield event.plain_result("?? 未找到相关视频资源")
                        return

                    # 存储当前结果和页数信息
                    self.current_results[event.user_id] = parsed_result
                    self.current_pages[event.user_id] = 1

                    async for msg in self._paged_result_sender(event, event.user_id):
                        yield msg

        except aiohttp.ClientTimeout:
            yield event.plain_result("? 请求超时，请稍后重试")
        except Exception as e:
            self.context.logger.error(f"视频查询异常: {str(e)}")
            yield event.plain_result("? 服务暂时异常，请稍后再试")

    def _parse_html(self, html_content):
        """HTML解析专用方法"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')

        results = []
        for idx, item in enumerate(video_items[:8], 1):
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            dd_elements = item.select('dl > dd')
            for dd in dd_elements:
                for url in dd.text.split('#'):
                    if url.strip():
                        results.append(f"{idx}. 【{title}】 ?? {url.strip()}")

        return results

    async def _paged_result_sender(self, event, user_id, per_page=5):
        results = self.current_results.get(user_id, [])
        page = self.current_pages.get(user_id, 1)

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_results = results[start_idx:end_idx]

        if not page_results:
            yield event.plain_result("?? 没有更多的结果了")
            return

        result_msg = [
            "?? 查询结果：",
            "\n".join(page_results),
            "\n" + "*" * 25,
            "?? 输入页码以查看更多结果（每页显示5条），15秒内有效",
            "*" * 25
        ]
        yield event.plain_result("\n".join(result_msg))

        # 监听用户的页码输入
        try:
            async with asyncio.timeout(15):
                while True:
                    new_event = await event.wait_for_reply()
                    if new_event.text.isdigit():
                        new_page = int(new_event.text)
                        if 1 <= new_page <= (len(results) + per_page - 1) // per_page:
                            self.current_pages[user_id] = new_page
                            async for msg in self._paged_result_sender(event, user_id):
                                yield msg
                            break
                        else:
                            yield event.plain_result("?? 无效的页码，请输入有效的数字")
                    else:
                        yield event.plain_result("?? 请输入数字页码")
        except asyncio.TimeoutError:
            yield event.plain_result("?? 超过15秒未收到反馈，查询结束")

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        if not self.api_url_vod:
            yield event.plain_result("?? 普通视频服务未配置")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        if not self.api_url_18:
            yield event.plain_result("?? 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

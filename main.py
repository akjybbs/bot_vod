from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # 直接使用 api_url_vod 和 api_url_18
        self.api_urls_vod = config.get("api_url_vod", [])
        self.api_urls_18 = config.get("api_url_18", [])
        
        # 检查配置是否完整
        if not self.api_urls_vod or not self.api_urls_18:
            raise ValueError("请确保在配置中正确设置了 api_url_vod 和 api_url_18")

    async def _common_handler(self, event, api_urls, keyword):
        """通用请求处理核心逻辑"""
        results = []
        for api_url in api_urls:
            # URL编码处理
            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"
            try:
                # 异步HTTP请求
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        # HTTP状态码处理
                        if response.status != 200:
                            results.append(f"?? 服务暂时不可用（状态码 {response.status}），URL: {query_url}")
                            continue
                        # 响应内容处理
                        html_content = await response.text()
                        parsed_result = self._parse_html(html_content)
                        if parsed_result:
                            results.append(parsed_result)
            except aiohttp.ClientTimeout:
                results.append(f"? 请求超时，请稍后重试，URL: {query_url}")
            except Exception as e:
                self.context.logger.error(f"视频查询异常: {str(e)}，URL: {query_url}")
                results.append("? 服务暂时异常，请稍后再试，URL: {query_url}")

        if not results:
            yield event.plain_result("?? 未找到相关视频资源")
        else:
            final_message = ["?? 查询结果："]
            final_message.extend(results)
            final_message.append("\n" + "*" * 25)
            final_message.append("?? 重要观看提示：")
            final_message.append("1. 手机端：复制链接到浏览器地址栏打开")
            final_message.append("2. 电脑端：使用专业播放器打开链接")
            final_message.append("*" * 25)
            yield event.plain_result("\n".join(final_message))

    def _parse_html(self, html_content):
        """HTML解析专用方法"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')
        results = []
        for idx, item in enumerate(video_items[:8], 1):
            # 提取标题
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            # 提取播放链接
            dd_elements = item.select('dl > dd')
            for dd in dd_elements:
                for url in dd.text.split('#'):
                    if url.strip():
                        results.append(f"{idx}. 【{title}】\n   ?? {url.strip()}")
        return "\n".join(results) if results else None

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视资源搜索"""
        if not self.api_urls_vod:
            yield event.plain_result("?? 普通视频服务未配置")
            return
        async for msg in self._common_handler(event, self.api_urls_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """18+视频搜索"""
        if not self.api_urls_18:
            yield event.plain_result("?? 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_urls_18, text):
            yield msg

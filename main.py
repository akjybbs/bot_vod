from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Video
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "")
        self.api_url_18 = config.get("api_url_18", "")

    async def _common_handler(self, event, api_url, keyword):
        """通用请求处理核心逻辑"""
        # 空API地址检查
        if not api_url:
            yield event.plain_result("⚠️ 服务未正确配置，请联系管理员")
            return

        # URL编码处理
        encoded_keyword = urllib.parse.quote(keyword)
        query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"

        try:
            # 异步HTTP请求
            async with aiohttp.ClientSession() as session:
                async with session.get(query_url, timeout=15) as response:
                    # HTTP状态码处理
                    if response.status != 200:
                        yield event.plain_result(f"⚠️ 服务暂时不可用（状态码 {response.status}）")
                        return

                    # 响应内容处理
                    html_content = await response.text()
                    parsed_result = self._parse_html(html_content)

                    if not parsed_result:
                        yield event.plain_result("🔍 未找到相关视频资源")
                        return

                    # 构建最终消息
                    result_msg = [
                        "📺 查询结果：",
                        parsed_result,
                        "\n" + "*" * 25,
                        "💡 重要观看提示：",
                        "1. 手机端：复制链接到浏览器地址栏打开",
                        "2. 电脑端：使用专业播放器打开链接",
                        "*" * 25
                    ]
                    yield event.plain_result("\n".join(result_msg))

        except aiohttp.ClientTimeout:
            yield event.plain_result("⏳ 请求超时，请稍后重试")
        except Exception as e:
            self.context.logger.error(f"视频查询异常: {str(e)}")
            yield event.plain_result("❌ 服务暂时异常，请稍后再试")

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
                        video = Video.fromURL(url=url.strip())
                        # 假设您想要保存视频对象的一些信息
                        results.append(f"{idx}. 【{title}】🎬 {str(video)}")

        return "\n".join(results) if results else None

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视资源搜索"""
        if not self.api_url_vod:
            yield event.plain_result("🔧 普通视频服务未配置")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """18+视频搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

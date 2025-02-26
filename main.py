from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "从API获取视频地址。使用 /vod 或 /vodd 电影名。请勿使用非法接口！", "1.0")
class SetuPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "")
        self.api_url_18 = config.get("api_url_18", "")
    
    async def _common_vod_handler(self, event, api_url, text):
        """通用视频处理逻辑"""
        if not api_url:
            yield event.plain_result("\n该服务未配置API地址")
            return

        encoded_text = urllib.parse.quote(text)
        query_url = f"{api_url}?ac=videolist&wd={encoded_text}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(query_url, timeout=15) as response:
                    if response.status != 200:
                        yield event.plain_result(f"\n请求失败，状态码: {response.status}")
                        return
                    
                    html_content = await response.text()
                    result = self._process_html(html_content)
                    
                    if not result:
                        yield event.plain_result("\n没有找到相关视频。")
                        return
                    
                    # 组装最终响应
                    msg = f"查询结果:\n{result}\n"
                    msg += "          ************************\n"
                    msg += "重要提示：\n请勿直接点击微信中的视频地址，微信会拦截！\n"
                    msg += "1.手机端将复制的播放链接粘贴到浏览器地址栏中进行观看。\n"
                    msg += "2.电脑端将复制的播放链接粘贴到播放器中观看！\n"
                    msg += "         ************************"
                    yield event.plain_result(msg)
        
        except aiohttp.ClientTimeout:
            yield event.plain_result("\n请求超时，请稍后再试")
        except Exception as e:
            yield event.plain_result("\n发生未知错误，请稍后再试。")

    def _process_html(self, html_content):
        """HTML解析逻辑"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')
        
        results = []
        for index, video in enumerate(video_items[:8], start=1):
            name = video.select_one('name').text if video.select_one('name') else '未知标题'
            dds = video.select('dl > dd')
            
            for dd in dds:
                urls = dd.text.split('#')
                for url in urls:
                    if url.strip():
                        results.append(f"{index}. 标题: {name}, 链接: {url}\n")
        
        return "\n".join(results) if results else None

    @filter.command("vod")
    async def vod_normal(self, event: AstrMessageEvent, text: str):
        """普通视频查询"""
        async for msg in self._common_vod_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def vod_adult(self, event: AstrMessageEvent, text: str):
        """18+视频查询"""
        async for msg in self._common_vod_handler(event, self.api_url_18, text):
            yield msg

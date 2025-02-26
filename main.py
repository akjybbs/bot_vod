from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "从API获取视频地址。使用 /vod 电影名。请勿使用非法接口！", "1.0")
class SetuPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url = config.get("api_url", "")

    @filter.command("vod")
    async def vod(self, event: AstrMessageEvent, text: str):
        # 检查是否配置了API URL
        if not self.api_url:
            yield event.plain_result("\n请先在配置文件中设置API地址")
            return
        
        # 对用户输入进行URL编码
        encoded_text = urllib.parse.quote(text)
        query_url = f"{self.api_url}?ac=videolist&wd={encoded_text}"

        try:
            # 使用aiohttp进行异步HTTP请求
            async with aiohttp.ClientSession() as session:
                async with session.get(query_url, timeout=15) as response:
                    response_text = await response.text()

                    if response.status == 200:
                        result = self.process_html_response(response_text)
                        if result:
                            yield event.plain_result(f"查询结果:\n{result}\n*************************\n播放方法：\n1.手机端将复制的播放链接粘贴到浏览器地址栏中进行观看。\n2.电脑端将复制的播放链接粘贴到播放器中观看！\n*************************")
                        else:
                            yield event.plain_result("\n没有找到相关视频。")
                    elif response.status == 404:
                        yield event.plain_result("\n请求的资源不存在，请检查请求路径是否正确。")
                    else:
                        yield event.plain_result(f"\n请求失败，状态码: {response.status}")
        except Exception as e:
            yield event.plain_result("\n发生未知错误，请稍后再试。")

    def process_html_response(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')  # 根据实际HTML结构调整选择器

        results = []
        for index, video in enumerate(video_items[:8], start=1):  # 只取前8条结果
            name = video.select_one('name').text if video.select_one('name') else '未知标题'
            dds = video.select('dl > dd')
            for dd in dds:
                urls = dd.text.split('#')
                for url in urls:
                    if url.strip() != '':
                        results.append(f"{index}. 标题: {name}, 链接: {url}\n")

        return "\n".join(results) if results else None

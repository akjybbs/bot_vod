from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
import logging
from bs4 import BeautifulSoup

# 设置日志记录级别
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@register("bot_vod", "appale", "从API获取视频地址。使用 /vod 电影名", "1.0")
class SetuPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url = config.get("api_url", "")

    @filter.command("vod")
    async def vod(self, event: AstrMessageEvent, text: str):
        # 检查是否配置了API URL
        if not self.api_url:
            logger.error("API URL未配置，请先在配置文件中设置API地址")
            yield event.plain_result("\n请先在配置文件中设置API地址")
            return
        
        # 对用户输入进行URL编码
        encoded_text = urllib.parse.quote(text)
        query_url = f"{self.api_url}?ac=videolist&wd={encoded_text}"
        logger.info(f"查询API的URL: {query_url}")

        try:
            # 使用aiohttp进行异步HTTP请求
            async with aiohttp.ClientSession() as session:
                async with session.get(query_url, timeout=15) as response:
                    response_text = await response.text()
                    logger.info(f"响应体: {response_text}")  # 直接输出响应体

                    if response.status == 200:
                        result = self.process_html_response(response_text)
                        if result:
                            yield event.plain_result(f"\n查询结果:\n{result}")
                        else:
                            yield event.plain_result("\n没有找到相关视频。")
                    elif response.status == 404:
                        logger.error(f"请求的资源不存在，状态码: {response.status}, 响应体: {response_text}")
                        yield event.plain_result("\n请求的资源不存在，请检查请求路径是否正确。")
                    else:
                        logger.error(f"请求失败，状态码: {response.status}, 响应体: {response_text}")
                        yield event.plain_result(f"\n请求失败，状态码: {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"请求失败: {e}")
            yield event.plain_result("\n请求失败，请稍后再试。")
        except Exception as e:
            logger.error(f"未知错误: {e}")
            yield event.plain_result("\n发生未知错误，请稍后再试。")

    def process_html_response(self, html_content):
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            video_items = soup.select('rss list video')  # 根据实际HTML结构调整选择器
            if not video_items:
                logger.error("HTML响应中未找到任何视频项")
                return None

            results = []
            for video in video_items:
                name = video.select_one('name').text if video.select_one('name') else '未知标题'
                pic = video.select_one('pic').get('src') if video.select_one('pic') else ''
                actor = video.select_one('actor').text if video.select_one('actor') else ''
                des = video.select_one('des').text if video.select_one('des') else ''

                dds = video.select('dl > dd')
                for dd in dds:
                    ddflag = dd.get('flag', '')
                    urls = dd.text.split('#')
                    for url in urls:
                        if url.strip() != '':
                            js = '第' + str(urls.index(url) + 1) + '集' if len(urls) > 1 else '完整版'
                            results.append(f"来源: {ddflag}\n标题: {name} - {js}, 链接: {url}\n")

            return "\n".join(results) if results else None
        except Exception as e:
            logger.error(f"HTML解析错误: {e}, 响应体: {html_content}")
            return None

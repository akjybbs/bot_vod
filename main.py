from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import json
import xml.etree.ElementTree as ET
import urllib.parse
import logging

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
            yield event.plain_result("\n请先在配置文件中设置API地址")
            return
        
        # 对用户输入进行URL编码
        encoded_text = urllib.parse.quote(text)
        query_url = f"{self.api_url}?ac=videolist&wd={encoded_text}"
        logger.info(f"Querying API with URL: {query_url}")

        try:
            # 使用aiohttp进行异步HTTP请求
            async with aiohttp.ClientSession() as session:
                async with session.get(query_url, timeout=15) as response:
                    content_type = response.headers.get('Content-Type', '').lower()
                    
                    if response.status == 200:
                        if 'json' in content_type:
                            data = await response.json()
                            result = self.process_json_response(data)
                        elif 'xml' in content_type:
                            data = await response.text()
                            result = self.process_xml_response(data)
                        else:
                            yield event.plain_result("\n不支持的响应格式，请检查API文档。")
                            return
                        
                        if result:
                            yield event.plain_result(f"\n查询结果:\n{result}")
                        else:
                            yield event.plain_result("\n没有找到相关视频。")
                    else:
                        yield event.plain_result(f"\n请求失败，状态码: {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"Request failed: {e}")
            yield event.plain_result("\n请求失败，请稍后再试。")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            yield event.plain_result("\nAPI响应解析失败，请检查API文档。")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            yield event.plain_result("\n发生未知错误，请稍后再试。")

    def process_json_response(self, data):
        if not data or 'list' not in data:
            return None

        video_list = data['list']
        if not video_list:
            return None

        return "\n".join([
            f"标题: {item['vod_name']}, 链接: {item['vod_play_url']}"
            for item in video_list
        ])

    def process_xml_response(self, data):
        try:
            root = ET.fromstring(data)
            video_list = root.findall(".//video")
            if not video_list:
                return None

            return "\n".join([
                f"标题: {video.find('name').text}, 链接: {video.find('play_url').text}"
                for video in video_list
            ])
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return None

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
                    content_type = response.headers.get('Content-Type', '').lower()
                    response_text = await response.text()
                    logger.info(f"响应的Content-Type: {content_type}")
                    logger.info(f"响应体（前500个字符）: {response_text[:500]}")  # 只打印前500个字符
                    
                    if response.status == 200:
                        if 'json' in content_type:
                            try:
                                data = json.loads(response_text)
                                result = self.process_json_response(data)
                            except json.JSONDecodeError as e:
                                logger.error(f"JSON解析错误: {e}, 响应体: {response_text}")
                                yield event.plain_result("\nAPI响应解析失败，请检查API文档。")
                                return
                        elif 'xml' in content_type.split(';')[0]:
                            try:
                                result = self.process_xml_response(response_text)
                            except ET.ParseError as e:
                                logger.error(f"XML解析错误: {e}, 响应体: {response_text}")
                                yield event.plain_result("\nAPI响应解析失败，请检查API文档。")
                                return
                        else:
                            logger.error(f"不支持的响应格式: {content_type}, 响应体: {response_text}")
                            yield event.plain_result(f"不支持的响应格式: {content_type}, 响应体: {response_text}")
                            return
                        
                        if result:
                            yield event.plain_result(f"\n查询结果:\n{result}")
                        else:
                            yield event.plain_result("\n没有找到相关视频。")
                    else:
                        logger.error(f"请求失败，状态码: {response.status}, 响应体: {response_text}")
                        yield event.plain_result(f"\n请求失败，状态码: {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"请求失败: {e}")
            yield event.plain_result("\n请求失败，请稍后再试。")
        except Exception as e:
            logger.error(f"未知错误: {e}")
            yield event.plain_result("\n发生未知错误，请稍后再试。")

    def process_json_response(self, data):
        if not data or 'list' not in data:
            logger.error("JSON响应中缺少必要的字段: list")
            return None

        video_list = data['list']
        if not video_list:
            logger.error("JSON响应中的视频列表为空")
            return None

        results = []
        for item in video_list:
            if 'vod_name' in item and 'vod_play_url' in item:
                results.append(f"标题: {item['vod_name']}, 链接: {item['vod_play_url']}")
            else:
                logger.error(f"视频项缺少必要字段: {item}")

        return "\n".join(results)

    def process_xml_response(self, data):
        try:
            root = ET.fromstring(data)
            video_items = root.findall(".//video")
            if not video_items:
                logger.error("XML响应中未找到任何视频项")
                return None

            results = []
            for video in video_items:
                title = video.find('name').text if video.find('name') is not None else '未知标题'
                # 查找包含视频链接的<dd>标签
                dd_elements = video.findall('.//dd')
                video_url = None
                for dd in dd_elements:
                    if dd.attrib.get('flag') == 'ckplayer':
                        # 提取CDATA部分的内容
                        video_url = dd.text.strip()
                        break
                if video_url:
                    results.append(f"标题: {title}, 链接: {video_url}")
                else:
                    logger.error(f"视频项中未找到带有flag='ckplayer'的<dd>标签: {ET.tostring(video)}")
            
            return "\n".join(results) if results else None
        except ET.ParseError as e:
            logger.error(f"XML解析错误: {e}, 响应体: {data}")
            return None

from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import json
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
                    content_type = response.headers.get('Content-Type', '').lower()
                    response_text = await response.text()
                    logger.info(f"响应的Content-Type: {content_type}")
                    logger.info(f"响应体: {response_text}")  # 直接输出响应体

                    if response.status == 200:
                        result = None
                        if 'json' in content_type:
                            result = self.process_json_response(response_text)
                        elif 'xml' in content_type.split(';')[0]:
                            result = self.process_xml_response(response_text)
                        elif 'html' in content_type.split(';')[0]:
                            result = self.process_html_response(response_text)
                        else:
                            logger.error(f"不支持的响应格式: {content_type}, 响应体: {response_text}")
                            yield event.plain_result("\n不支持的响应格式，请检查API文档。")
                            return
                        
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

    def process_json_response(self, data):
        try:
            jsondata = json.loads(data, strict=False)
            if jsondata and 'list' in jsondata:
                medialist = jsondata['list']
                if len(medialist) > 0:
                    results = []
                    for info in medialist:
                        playfrom = info["vod_play_from"]
                        playnote = '$$$'
                        playfromlist = playfrom.split(playnote)
                        playurl = info["vod_play_url"]
                        playurllist = playurl.split(playnote)
                        
                        for i in range(len(playfromlist)):
                            urllist = playurllist[i].split('#')
                            for url in urllist:
                                if url.strip() != '':
                                    jsdz = url
                                    js = '第' + str(urllist.index(url) + 1) + '集' if len(urllist) > 1 else '完整版'
                                    results.append(f"来源: {playfromlist[i]}\n标题: {info['vod_name']} - {js}, 链接: {jsdz}\n")
                    
                    return "\n".join(results) if results else None
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}, 响应体: {data}")
            return None

    def process_xml_response(self, data):
        try:
            soup = BeautifulSoup(data, 'xml')
            video_items = soup.find_all('video')
            if not video_items:
                logger.error("XML响应中未找到任何视频项")
                return None

            results = []
            for video in video_items:
                name = video.find('name').text if video.find('name') is not None else '未知标题'
                pic = video.find('pic').text if video.find('pic') is not None else ''
                actor = video.find('actor').text if video.find('actor') is not None else ''
                des = video.find('des').text if video.find('des') is not None else ''

                dds = video.find_all('dd')
                for dd in dds:
                    ddflag = dd.get('flag', '')
                    urls = dd.text.split('#')
                    for url in urls:
                        if url.strip() != '':
                            js = '第' + str(urls.index(url) + 1) + '集' if len(urls) > 1 else '完整版'
                            results.append(f"来源: {ddflag}\n标题: {name} - {js}, 链接: {url}\n")

            return "\n".join(results) if results else None
        except Exception as e:
            logger.error(f"XML解析错误: {e}, 响应体: {data}")
            return None

    def process_html_response(self, html_content):
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            selector = soup.select('rss > list > video')
            if len(selector) > 0:
                info = selector[0]
                nameinfo = info.select('name')[0]
                name = nameinfo.text
                picinfo = info.select('pic')[0]
                pic = picinfo.text
                actorinfo = info.select('actor')[0]
                actor = '演员:' + actorinfo.text.strip()
                desinfo = info.select('des')[0]
                des = '简介:' + desinfo.text.strip()
                dds = info.select('dl > dd')
                results = []
                for dd in dds:
                    ddflag = dd.get('flag')
                    ddinfo = dd.text
                    m3u8list = []
                    if ddflag.find('m3u8') >= 0:
                        urllist = ddinfo.split('#')
                        n = 1
                        for source in urllist:
                            urlinfo = source.split('$')
                            if len(urlinfo) == 1:
                                m3u8list.append({'title': f'第{n}集', 'url': ddinfo})
                            else:
                                m3u8list.append({'title': urlinfo[0], 'url': urlinfo[1]})
                            n += 1
                        results.append(f"来源: {ddflag}\n")
                        for media in m3u8list:
                            results.append(f"标题: {media['title']}, 链接: {media['url']}\n")
                return "\n".join(results) if results else None
        except Exception as e:
            logger.error(f"HTML解析错误: {e}, 响应体: {html_content}")
            return None

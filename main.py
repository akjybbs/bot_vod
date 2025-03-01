from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
from collections import OrderedDict

@register("bot_vod", "appale", "精准影视搜索（分链接模式）", "2.0")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))

    async def _common_handler(self, event, api_urls, keyword):
        """跨API合并相同标题资源"""
        merged_data = OrderedDict()
        
        # 第一阶段：收集所有API数据
        for api_url in api_urls:
            api_url = api_url.strip()
            if not api_url:
                continue
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{api_url}?ac=videolist&wd={urllib.parse.quote(keyword)}", 
                        timeout=15
                    ) as response:
                        if response.status != 200:
                            continue
                            
                        soup = BeautifulSoup(await response.text(), 'html.parser')
                        # 解析当前API结果
                        for video in soup.select('rss list video')[:self.records]:
                            title = (video.select_one('name').text.strip() 
                                     if video.select_one('name') 
                                     else "未知标题")
                            urls = []
                            for dd in video.select('dl > dd'):
                                urls.extend(url.strip() 
                                           for url in dd.text.split('#') 
                                           if url.strip())
                            
                            # 合并到全局数据
                            if title not in merged_data:
                                merged_data[title] = {
                                    'index': len(merged_data) + 1,
                                    'urls': []
                                }
                            merged_data[title]['urls'].extend(urls)

            except Exception as e:
                self.context.logger.error(f"API请求异常: {str(e)}")

        # 第二阶段：生成最终输出
        output_lines = []
        for title in merged_data:
            entry = merged_data[title]
            for url in entry['urls'][:self.records]:  # 控制单个标题最大链接数
                output_lines.append(
                    f"{entry['index']}. 【{title[:20]}】\n   🎬 {url}"
                )
                if len(output_lines) >= self.records:  # 全局控制总条数
                    break
            if len(output_lines) >= self.records:
                break

        # 构建结果消息
        result = [
            f"🔍 搜索 {len(api_urls)} 个源｜找到 {len(output_lines)} 条资源",
            *output_lines,
            "━" * 25 + "\n💡 相同序号表示同一影视的不同链接源"
        ]
        yield event.plain_result("\n".join(result))

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视搜索"""
        if not self.api_url_vod:
            yield event.plain_result("🎦 视频服务维护中")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """🔞成人内容搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞 功能未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

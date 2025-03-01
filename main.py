from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "影视资源搜索（分链接显示）", "1.2")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))

    async def _common_handler(self, event, api_urls, keyword):
        """核心处理逻辑（严格分链接显示）"""
        total_attempts = len(api_urls)
        successful_apis = 0
        all_entries = []
        
        for api_url in api_urls:
            api_url = api_url.strip()
            if not api_url:
                continue

            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        if response.status != 200:
                            continue
                            
                        html_content = await response.text()
                        entries = self._parse_api_results(html_content)
                        
                        if entries:
                            successful_apis += 1
                            all_entries.extend(entries[:self.records])  # 严格限制每个API的输出数量
            except Exception as e:
                self.context.logger.error(f"请求异常: {str(e)}")

        # 生成最终结果
        output = []
        current_group = []
        for entry in all_entries:
            line = f"{entry['group_id']}. 【{entry['title']}】\n   🎬 {entry['url']}"
            output.append(line)
        
        result = [
            f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
            *output,
            "━" * 25 + "\n💡 提示：相同序号表示同一影视的不同链接"
        ]
        yield event.plain_result("\n".join(result))

    def _parse_api_results(self, html_content):
        """严格解析API结果（每个链接单独显示）"""
        soup = BeautifulSoup(html_content, 'html.parser')
        videos = soup.select('rss list video')[:self.records]
        
        entries = []
        title_groups = {}  # 记录标题分组
        
        for video in videos:
            title = video.select_one('name').text.strip() if video.select_one('name') else "未知标题"
            urls = []
            
            # 提取所有链接
            for dd in video.select('dl > dd'):
                urls.extend(url.strip() for url in dd.text.split('#') if url.strip())
            
            # 创建分组
            if title not in title_groups:
                title_groups[title] = len(title_groups) + 1
            group_id = title_groups[title]
            
            # 每个链接生成独立条目
            for url in urls:
                entries.append({
                    "group_id": group_id,
                    "title": title,
                    "url": url
                })
        
        return entries

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

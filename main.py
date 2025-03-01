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
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))

    async def _common_handler(self, event, api_urls, keyword):
        """改进：新增标题去重逻辑"""
        total_attempts = len(api_urls)
        successful_apis = 0
        all_entries = []  # 存储结构化数据

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
                        parsed_entries, _ = self._parse_html(html_content)
                        if parsed_entries:
                            successful_apis += 1
                            all_entries.extend(parsed_entries)

            except Exception as e:
                self.context.logger.error(f"请求异常: {str(e)}")
                continue

        # 去重逻辑：按标题保留唯一
        seen_titles = set()
        unique_entries = []
        for entry in all_entries:
            if entry['title'] not in seen_titles:
                seen_titles.add(entry['title'])
                unique_entries.append(entry)
        
        # 构建结果消息
        total_videos = len(unique_entries)
        if unique_entries:
            result_lines = []
            for idx, entry in enumerate(unique_entries, 1):
                result_lines.append(f"{idx}. 【{entry['title']}】\n   🎬 {entry['url']}")
            
            msg_body = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                f"📊 找到 {total_videos} 条去重后结果",
                "━" * 25,
                "📺 查询结果：",
                *result_lines,
                "\n" + "━" * 25,
                "💡 观看提示：同名资源已自动去重",
                "━" * 25
            ]
            yield event.plain_result("\n".join(msg_body))
        else:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━' * 25}🔍 没有找到相关资源")

    def _parse_html(self, html_content):
        """改进：返回结构化数据"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')

        entries = []
        for item in video_items[:self.records]:
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            for dd in item.select('dl > dd'):
                for url in dd.text.split('#'):
                    if url.strip():
                        entries.append({'title': title, 'url': url.strip()})
        
        return entries, len(entries)

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        if not any(self.api_url_vod):
            yield event.plain_result("🔧 服务未配置")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        if not any(self.api_url_18):
            yield event.plain_result("🔞 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

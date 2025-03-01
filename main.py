from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
from collections import defaultdict

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))

    async def _common_handler(self, event, api_urls, keyword):
        total_attempts = len(api_urls)
        successful_apis = 0
        all_entries = []
        total_videos = 0

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
                        parsed_entries, video_count = self._parse_html(html_content)

                        if parsed_entries:
                            successful_apis += 1
                            total_videos += video_count
                            all_entries.extend(parsed_entries)

            except aiohttp.ClientTimeout:
                continue
            except Exception as e:
                self.context.logger.error(f"视频查询异常: {str(e)}")
                continue

        # 按标题分组并去重
        grouped = defaultdict(list)
        for entry in all_entries:
            grouped[entry['title']].append(entry['url'])

        # 生成结果字符串
        results = []
        for idx, (title, urls) in enumerate(grouped.items(), 1):
            results.append(f"{idx}. 【{title}】")
            for url in urls:
                results.append(f"   🎬 {url}")

        combined_results = "\n".join(results) if results else None
        total_videos = sum(len(urls) for urls in grouped.values())

        if combined_results:
            result_msg = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n📊 为你找到 {total_videos} 条视频\n{'━' * 25}",
                "📺 查询结果：",
                combined_results,
                "\n" + "━" * 25,
                "💡 重要观看提示：",
                "1. 移动端：直接粘贴链接到浏览器",
                "2. 桌面端：推荐使用PotPlayer/VLC",
                "━" * 25
            ]
            yield event.plain_result("\n".join(result_msg))
        else:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━' * 25}🔍 没有找到相关视频资源,请换个关键词重新搜索。")

    def _parse_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')

        entries = []
        video_count = 0

        for item in video_items[:self.records]:
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            dd_elements = item.select('dl > dd')
            for dd in dd_elements:
                for url in dd.text.split('#'):
                    url = url.strip()
                    if url:
                        entries.append({'title': title, 'url': url})
                        video_count += 1

        return entries, video_count

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        if not any(self.api_url_vod):
            yield event.plain_result("🔧 普通视频服务未配置")
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

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
        """合并多API结果的核心逻辑"""
        total_attempts = len(api_urls)
        successful_apis = 0
        grouped_results = {}  # 按标准化标题聚合结果
        ordered_titles = []   # 维护标准化标题的原始顺序
        
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
                        parsed_items = self._parse_html(html_content)
                        
                        if parsed_items:
                            successful_apis += 1
                            # 合并结果并保持顺序
                            for normalized_title, original_title, url in parsed_items:
                                if normalized_title not in grouped_results:
                                    grouped_results[normalized_title] = {
                                        'original_title': original_title,
                                        'urls': []
                                    }
                                    ordered_titles.append(normalized_title)
                                grouped_results[normalized_title]['urls'].append(url)

            except Exception as e:
                self.context.logger.error(f"API请求异常: {str(e)}")
                continue

        # 构建最终输出
        result_lines = []
        total_videos = sum(len(data['urls']) for data in grouped_results.values())
        
        for idx, normalized_title in enumerate(ordered_titles, 1):
            data = grouped_results[normalized_title]
            original_title = data['original_title']
            urls = data['urls']
            result_lines.append(f"{idx}. 【{original_title}】")
            result_lines.extend([f"   🎬 {url}" for url in urls])

        if result_lines:
            header = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                f"📊 找到 {total_videos} 条资源",
                "━" * 30
            ]
            footer = [
                "━" * 30,
                "💡 播放提示：",
                "1. 移动端直接粘贴链接到浏览器",
                "2. 电脑端推荐使用PotPlayer/VLC播放",
                "━" * 30
            ]
            full_msg = "\n".join(header + result_lines + footer)
            yield event.plain_result(full_msg)
        else:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源")

    def _parse_html(self, html_content):
        """解析HTML并返回结构化数据（标准化标题）"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')[:self.records]
        
        parsed_data = []
        for item in video_items:
            original_title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            normalized_title = original_title.lower().strip()  # 标准化处理
            # 提取所有播放链接
            for dd in item.select('dl > dd'):
                for url in dd.text.split('#'):
                    if url := url.strip():
                        parsed_data.append((normalized_title, original_title, url))
        return parsed_data

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视搜索"""
        if not self.api_url_vod:
            yield event.plain_result("⚠️ 普通视频服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """成人内容搜索"""
        if not self.api_url_18:
            yield event.plain_result("⚠️ 成人内容服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

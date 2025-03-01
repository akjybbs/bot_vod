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
        grouped_results = {}  # 按标题聚合结果
        ordered_titles = []   # 维护标题原始顺序
        
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
                            for title, url in parsed_items:
                                if title not in grouped_results:
                                    grouped_results[title] = []
                                    ordered_titles.append(title)
                                grouped_results[title].append(url)

            except Exception as e:
                self.context.logger.error(f"API请求异常: {str(e)}")
                continue

        # 构建最终输出
        result_lines = []
        total_videos = sum(len(urls) for urls in grouped_results.values())
        m3u8_flags = []
        
        for idx, title in enumerate(ordered_titles, 1):
            urls = grouped_results.get(title, [])
            result_lines.append(f"{idx}. 【{title}】")
            for url in urls:
                line = f"   🎬 {url}"
                result_lines.append(line)
                m3u8_flags.append(url.endswith('.m3u8'))

        if result_lines:
            header_lines = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                f"📊 找到 {total_videos} 条资源",
                "━" * 30
            ]
            footer_lines = [
                "━" * 30,
                "💡 播放提示：",
                "1. 移动端直接粘贴链接到浏览器",
                "2. 电脑端推荐使用PotPlayer/VLC播放",
                "━" * 30
            ]
            header_str = "\n".join(header_lines) + "\n"
            footer_str = "\n" + "\n".join(footer_lines)
            m3u8_indices = [i for i, flag in enumerate(m3u8_flags) if flag]
            
            pages = []
            current_start = 0
            while current_start < len(result_lines):
                possible_ends = [i for i in m3u8_indices if i >= current_start]
                if not possible_ends:
                    break  # 剩余行无m3u8链接，无法分页
                
                # 寻找最佳分页点
                best_end = None
                for end in reversed(possible_ends):
                    content_lines = result_lines[current_start:end+1]
                    content_length = sum(len(line) + 1 for line in content_lines)
                    total_length = len(header_str) + content_length + len(footer_str)
                    if total_length <= 1000:
                        best_end = end
                        break
                if best_end is None:
                    best_end = possible_ends[0]  # 强制分页，可能超长
                
                # 生成分页内容
                page_content = header_str + "\n".join(result_lines[current_start:best_end+1]) + footer_str
                pages.append(page_content)
                current_start = best_end + 1

            # 发送分页消息
            for page in pages:
                yield event.plain_result(page)
        else:
            msg = f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源"
            yield event.plain_result(msg)

    def _parse_html(self, html_content):
        """解析HTML并返回结构化数据"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')[:self.records]
        
        parsed_data = []
        for item in video_items:
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            # 提取所有播放链接
            for dd in item.select('dl > dd'):
                for url in dd.text.split('#'):
                    if url := url.strip():
                        parsed_data.append((title, url))
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
        """🔞内容搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞成人内容服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

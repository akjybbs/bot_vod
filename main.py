from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
import time
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.pagination_cache = {}

    def _split_into_pages(self, header, result_lines, footer):
        pages = []
        current_chunk = []
        current_length = 0
        
        header_str = '\n'.join(header)
        footer_str = '\n'.join(footer)
        header_footer = header_str + '\n' + footer_str
        hf_length = len(header_footer)
        max_content_length = 1000 - hf_length - 2  # 预留换行符空间

        for line in result_lines:
            temp_chunk = current_chunk + [line]
            temp_content = '\n'.join(temp_chunk)
            
            if len(temp_content) > max_content_length:
                # 寻找最后包含m3u8的行
                split_index = None
                for i in reversed(range(len(current_chunk))):
                    if 'm3u8' in current_chunk[i]:
                        split_index = i + 1
                        break
                
                if split_index is None:
                    split_index = len(current_chunk)
                
                page_chunk = current_chunk[:split_index]
                page_content = '\n'.join(header + page_chunk + footer)
                pages.append(page_content)
                
                current_chunk = current_chunk[split_index:] + [line]
            else:
                current_chunk = temp_chunk

        if current_chunk:
            # 确保最后一行是m3u8
            last_m3u8 = None
            for i in reversed(range(len(current_chunk))):
                if 'm3u8' in current_chunk[i]:
                    last_m3u8 = i + 1
                    break
            
            if last_m3u8 is not None:
                valid_chunk = current_chunk[:last_m3u8]
                remaining = current_chunk[last_m3u8:]
            else:
                valid_chunk = current_chunk
                remaining = []

            if valid_chunk:
                page_content = '\n'.join(header + valid_chunk + footer)
                pages.append(page_content)
            
            if remaining:
                page_content = '\n'.join(header + remaining + footer)
                pages.append(page_content)

        return pages or ['\n'.join(header + footer)]

    async def _common_handler(self, event, api_urls, keyword):
        total_attempts = len(api_urls)
        successful_apis = 0
        grouped_results = {}
        ordered_titles = []
        
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
                            for title, url in parsed_items:
                                if title not in grouped_results:
                                    grouped_results[title] = []
                                    ordered_titles.append(title)
                                grouped_results[title].append(url)

            except Exception as e:
                self.context.logger.error(f"API请求异常: {str(e)}")
                continue

        result_lines = []
        total_videos = sum(len(urls) for urls in grouped_results.values())
        
        for idx, title in enumerate(ordered_titles, 1):
            urls = grouped_results.get(title, [])
            result_lines.append(f"{idx}. 【{title}】")
            result_lines.extend([f"   🎬 {url}" for url in urls])

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

        if result_lines:
            pages = self._split_into_pages(header, result_lines, footer)
        else:
            pages = [f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源"]

        return pages

    def _parse_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')[:self.records]
        
        parsed_data = []
        for item in video_items:
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            for dd in item.select('dl > dd'):
                for url in dd.text.split('#'):
                    if url := url.strip():
                        parsed_data.append((title, url))
        return parsed_data

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        if not self.api_url_vod:
            yield event.plain_result("⚠️ 普通视频服务未启用")
            return
        
        pages = await self._common_handler(event, self.api_url_vod, text)
        user_id = event.user_id  # 根据实际接口获取用户ID
        self.pagination_cache[user_id] = {
            "pages": pages,
            "timestamp": time.time()
        }
        
        yield event.plain_result(pages[0])
        if len(pages) > 1:
            yield event.plain_result(f"【分页提示】回复2-{len(pages)}查看后续内容（20秒内有效）")

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        if not self.api_url_18:
            yield event.plain_result("🔞成人内容服务未启用")
            return
        
        pages = await self._common_handler(event, self.api_url_18, text)
        user_id = event.user_id  # 根据实际接口获取用户ID
        self.pagination_cache[user_id] = {
            "pages": pages,
            "timestamp": time.time()
        }
        
        yield event.plain_result(pages[0])
        if len(pages) > 1:
            yield event.plain_result(f"【分页提示】回复2-{len(pages)}查看后续内容（20秒内有效）")

    @filter.regex(r"^\d+$")
    async def handle_pagination(self, event: AstrMessageEvent):
        user_id = event.user_id
        cache = self.pagination_cache.get(user_id)
        
        if not cache or (time.time() - cache["timestamp"]) > 20:
            return
        
        try:
            page_num = int(event.message.text.strip())
        except ValueError:
            return
        
        pages = cache["pages"]
        if 1 < page_num <= len(pages):
            yield event.plain_result(pages[page_num - 1])
        elif page_num == 1:
            yield event.plain_result("已经是第一页啦")
        else:
            yield event.plain_result(f"无效页码，请输入2-{len(pages)}之间的数字")

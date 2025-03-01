from typing import Dict
from astrbot.api.all import *
from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
from typing import Dict

# 用户状态跟踪，记录分页信息和时间戳
USER_STATES: Dict[str, Dict] = {}

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))

    def _split_into_pages(self, lines: list) -> list:
        """将结果分页，每页最后一行以m3u8结尾且不超过1000字符"""
        pages = []
        current_page = []
        current_length = 0
        last_m3u8 = -1

        for line in lines:
            line_len = len(line) + 1  # 包含换行符
            # 预判添加后是否超限
            if current_length + line_len > 1000:
                if last_m3u8 != -1:
                    # 切割到最后一个m3u8位置
                    valid_page = current_page[:last_m3u8+1]
                    pages.append(valid_page)
                    # 处理剩余内容
                    current_page = current_page[last_m3u8+1:] + [line]
                    current_length = sum(len(l)+1 for l in current_page)
                    # 重置最后位置
                    last_m3u8 = -1
                    # 检查现有内容
                    for idx, l in enumerate(current_page):
                        if l.strip().endswith('.m3u8'):
                            last_m3u8 = idx
                else:
                    # 强制分页（不符合要求）
                    pages.append(current_page)
                    current_page = [line]
                    current_length = line_len
                    last_m3u8 = -1 if not line.strip().endswith('.m3u8') else 0
            else:
                current_page.append(line)
                current_length += line_len
                if line.strip().endswith('.m3u8'):
                    last_m3u8 = len(current_page) - 1

        # 处理最后一页
        if current_page:
            if last_m3u8 != -1:
                pages.append(current_page[:last_m3u8+1])
                # 递归处理剩余行
                pages += self._split_into_pages(current_page[last_m3u8+1:])
            else:
                pages.append(current_page)

        return pages

    async def _common_handler(self, event, api_urls, keyword):
        """合并多API结果并分页的核心逻辑"""
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

        # 构建结果
        result_lines = []
        total_videos = sum(len(urls) for urls in grouped_results.values())
        
        for idx, title in enumerate(ordered_titles, 1):
            urls = grouped_results.get(title, [])
            result_lines.append(f"{idx}. 【{title}】")
            result_lines.extend([f"   🎬 {url}" for url in urls])

        # 分页逻辑
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

        if not result_lines:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源")
            return

        # 分页处理
        pages = self._split_into_pages(result_lines)
        constructed_pages = []
        total_pages = len(pages)

        for idx, page in enumerate(pages, 1):
            content = []
            if idx == 1:
                content.extend(header)
            content.extend(page)
            if idx == total_pages:
                content.extend(footer)
            
            # 添加分页信息
            page_info = f"📄 第 {idx}/{total_pages} 页"
            if idx < total_pages:
                content.append(f"{page_info}\n回复数字继续查看（20秒内有效）")
            else:
                content.append(page_info)
            
            constructed_page = "\n".join(content)
            constructed_pages.append(constructed_page)

        # 存储用户状态
        user_id = str(event.user_id)
        USER_STATES[user_id] = {
            "pages": constructed_pages,
            "timestamp": time.time(),
            "total": total_pages
        }

        # 发送第一页
        yield event.plain_result(constructed_pages[0])

    def _parse_html(self, html_content):
        """解析HTML并返回结构化数据"""
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

    @filter.text
    async def handle_pagination(self, event: AstrMessageEvent, text: str):
        """处理分页请求"""
        user_id = str(event.user_id)
        state = USER_STATES.get(user_id)

        if not state:
            return

        # 检查超时
        if time.time() - state["timestamp"] > 20:
            del USER_STATES[user_id]
            return

        # 验证输入
        if not text.isdigit():
            return
        
        page_num = int(text)
        if not 1 <= page_num <= state["total"]:
            yield event.plain_result(f"⚠️ 页码无效（1-{state['total']}）")
            del USER_STATES[user_id]
            return

        # 发送对应页
        yield event.plain_result(state["pages"][page_num-1])
        del USER_STATES[user_id]

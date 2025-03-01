from typing import Dict
from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.types import EventMessageType
import aiohttp
import urllib.parse
import asyncio
import time
from bs4 import BeautifulSoup

# 分页状态存储结构
VIDEO_PAGES: Dict[int, Dict] = {}

@register("bot_vod", "appale", "分页影视搜索（/vod 电影名）", "2.0")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.page_timeout = 20  # 分页超时时间

    async def _common_handler(self, event, api_urls, keyword):
        """带分页的请求处理核心方法"""
        # 原始API请求逻辑
        total_attempts = len(api_urls)
        successful_apis = 0
        grouped_results = {}
        ordered_titles = []
        
        # 遍历所有API源
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

        # 构建结果列表
        result_lines = []
        for idx, title in enumerate(ordered_titles, 1):
            urls = grouped_results.get(title, [])
            result_lines.append(f"{idx}. 【{title}】")
            result_lines.extend([f"   🎬 {url}" for url in urls])

        # 生成分页内容
        pages = self._build_pages(
            total_attempts=total_attempts,
            successful_apis=successful_apis,
            total_results=sum(len(urls) for urls in grouped_results.values()),
            result_lines=result_lines
        )

        if not pages:
            yield event.plain_result("未找到相关资源")
            return

        # 存储分页状态
        user_id = event.get_sender_id()
        VIDEO_PAGES[user_id] = {
            "pages": pages,
            "timestamp": time.time(),
            "total_pages": len(pages)
        }

        # 发送第一页
        yield event.plain_result(pages[0])

        # 设置超时清理
        self._schedule_cleanup(user_id)

    def _build_pages(self, total_attempts: int, successful_apis: int, total_results: int, result_lines: list) -> list:
        """智能分页构建器"""
        MAX_PAGE_LENGTH = 900  # 留出微信消息余量
        pages = []
        current_page = []
        current_length = 0
        
        # 构建页头
        header = [
            f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
            f"📊 找到 {total_results} 条资源",
            "━" * 30
        ]
        header_length = sum(len(line)+1 for line in header)
        
        # 构建页脚
        footer = [
            "━" * 30,
            "💡 播放提示：",
            "1. 移动端直接粘贴链接到浏览器",
            "2. 电脑端推荐使用PotPlayer/VLC播放",
            "━" * 30,
            f"📄 回复页码查看后续内容（{self.page_timeout}秒内有效）"
        ]
        footer_length = sum(len(line)+1 for line in footer) + 10  # 页码提示余量

        # 初始页
        current_page.extend(header)
        current_length = header_length
        page_num = 1

        for line in result_lines:
            line_length = len(line) + 1  # 换行符占1字符

            # 强制分页条件：遇到m3u8链接
            if ".m3u8" in line:
                if current_page and current_page[-1].startswith("📄"):
                    current_page.pop()  # 移除旧页码提示
                current_page.append(f"📄 当前第 {page_num} 页")
                full_page = "\n".join(current_page + footer)
                pages.append(full_page)
                
                # 重置页面
                page_num += 1
                current_page = header.copy()
                current_length = header_length
                continue

            # 常规分页检查
            if current_length + line_length + footer_length > MAX_PAGE_LENGTH:
                current_page.append(f"📄 当前第 {page_num} 页")
                full_page = "\n".join(current_page + footer)
                pages.append(full_page)
                
                # 重置页面
                page_num += 1
                current_page = header.copy()
                current_length = header_length

            # 添加内容
            current_page.append(line)
            current_length += line_length

        # 处理最后一页
        if len(current_page) > len(header):
            current_page.append(f"📄 当前第 {page_num} 页")
            full_page = "\n".join(current_page + footer)
            pages.append(full_page)

        return pages

    def _schedule_cleanup(self, user_id: int):
        """计划任务清理过期状态"""
        loop = asyncio.get_running_loop()
        loop.call_later(self.page_timeout, self._cleanup_page_state, user_id)

    def _cleanup_page_state(self, user_id: int):
        """实际清理状态"""
        if user_id in VIDEO_PAGES:
            if time.time() - VIDEO_PAGES[user_id]["timestamp"] > self.page_timeout:
                del VIDEO_PAGES[user_id]
                self.context.logger.debug(f"已清理用户 {user_id} 的分页状态")

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

    @filter.event_message_type(EventMessageType.TEXT)
    async def handle_page_request(self, event: AstrMessageEvent):
        """处理分页请求"""
        user_id = event.get_sender_id()
        message = event.message_str.strip()

        # 验证状态存在性
        if user_id not in VIDEO_PAGES:
            return

        # 验证是否为有效数字
        if not message.isdigit():
            return

        page_num = int(message)
        page_data = VIDEO_PAGES[user_id]

        # 验证页码范围
        if 1 <= page_num <= page_data["total_pages"]:
            # 更新状态时间戳
            VIDEO_PAGES[user_id]["timestamp"] = time.time()

            # 发送请求页
            yield event.plain_result(page_data["pages"][page_num-1])

            # 重置超时计时
            self._schedule_cleanup(user_id)

    def _parse_html(self, html_content: str) -> list:
        """HTML解析器"""
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

from astrbot.api.all import *
from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
from typing import Dict, List

PAGINATION_STATES: Dict[int, Dict] = {}

@register("bot_vod", "appale", "影视搜索（命令：/vod 或 /vodd + 关键词）", "2.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.max_page_length = 950  # 预留空间给分页导航

    async def _common_handler(self, event, api_urls, keyword):
        """核心搜索逻辑"""
        total_attempts = len(api_urls)
        successful_apis = 0
        grouped_results = {}
        ordered_titles = []
        
        # API请求处理
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

        # 构建分页数据
        result_lines = []
        m3u8_flags = []
        for idx, title in enumerate(ordered_titles, 1):
            urls = grouped_results.get(title, [])
            result_lines.append(f"{idx}. 【{title}】")
            for url in urls:
                result_lines.append(f"   🎬 {url}")
                m3u8_flags.append(url.endswith('.m3u8'))

        # 处理分页逻辑
        if result_lines:
            pages = self._generate_pages(result_lines, m3u8_flags)
            user_id = event.get_sender_id()
            
            PAGINATION_STATES[user_id] = {
                "pages": pages,
                "keyword": keyword,
                "search_type": "normal" if api_urls == self.api_url_vod else "adult",
                "timestamp": time.time()
            }
            
            # 发送第一页
            yield from self._send_page(event, 0, pages)
        else:
            msg = f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源"
            yield event.plain_result(msg)

    def _generate_pages(self, lines: List[str], m3u8_flags: List[bool]) -> List[List[str]]:
        """智能分页生成"""
        pages = []
        current_page = []
        current_length = 0
        last_m3u8_index = -1

        header = [
            "🔍 影视搜索结果",
            "━" * 30
        ]
        footer = [
            "━" * 30,
            "💡 播放提示：",
            "1. 移动端直接粘贴链接到浏览器",
            "2. 电脑端推荐使用PotPlayer/VLC播放",
            "━" * 30
        ]

        # 预计算基础长度
        base_length = len('\n'.join(header + footer)) + 50  # 预留导航空间

        for i, line in enumerate(lines):
            line_length = len(line) + 1  # 包含换行符
            is_m3u8 = m3u8_flags[i] if i < len(m3u8_flags) else False

            # 记录最后一个m3u8位置
            if is_m3u8:
                last_m3u8_index = i

            # 强制分页条件
            if current_length + line_length + base_length > self.max_page_length:
                # 寻找最佳分页点
                split_index = last_m3u8_index if last_m3u8_index >= len(current_page) else i
                if split_index > len(current_page):
                    current_page = lines[:split_index+1]
                    pages.append(header + current_page + footer)
                    lines = lines[split_index+1:]
                else:
                    pages.append(header + current_page + footer)
                    current_page = [line]
                
                current_length = line_length
                last_m3u8_index = -1
                continue

            current_page.append(line)
            current_length += line_length

        # 处理剩余内容
        if current_page:
            pages.append(header + current_page + footer)

        return pages

    async def _send_page(self, event, page_index: int, pages: List[List[str]]):
        """发送指定页码"""
        current_page = page_index + 1
        total_pages = len(pages)
        
        # 构建导航信息
        navigation = [
            f"📑 页码：{current_page}/{total_pages}",
            "回复数字跳转页面（20秒内有效）",
            "━" * 30
        ]
        
        # 插入导航到页脚前
        page_content = pages[page_index][:-3] + navigation + pages[page_index][-3:]
        yield event.plain_result('\n'.join(page_content))

    @filter.message_handle
    async def handle_pagination(self, event: AstrMessageEvent):
        """处理分页请求"""
        user_id = event.get_sender_id()
        message = event.message_str.strip()
        current_time = time.time()

        # 清理过期状态（超过20秒）
        expired_users = [uid for uid, s in PAGINATION_STATES.items() if current_time - s["timestamp"] > 20]
        for uid in expired_users:
            del PAGINATION_STATES[uid]

        # 检查是否存在有效状态
        if user_id not in PAGINATION_STATES:
            return MessageEventResult.IGNORE

        state = PAGINATION_STATES[user_id]
        state["timestamp"] = current_time  # 刷新时间戳

        # 处理数字输入
        if message.isdigit():
            page_num = int(message)
            total_pages = len(state["pages"])
            
            if 1 <= page_num <= total_pages:
                yield from self._send_page(event, page_num-1, state["pages"])
                return MessageEventResult.HANDLED
            else:
                yield event.plain_result(f"⚠️ 请输入1~{total_pages}之间的页码")
                return MessageEventResult.HANDLED

        # 处理非数字输入
        del PAGINATION_STATES[user_id]
        yield event.plain_result("❌ 分页导航已取消")
        return MessageEventResult.HANDLED

    def _parse_html(self, html_content):
        """解析HTML内容"""
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
        """成人内容搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞 成人内容服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

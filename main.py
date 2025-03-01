from astrbot.api.all import *
import aiohttp
import urllib.parse
import time
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "影视资源搜索插件", 2.0.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.pagination_cache = {}

    def _get_session_id(self, event):
        """跨平台用户标识获取"""
        try:
            # 微信开放平台专用字段
            return event.origin_user_id
        except AttributeError:
            try:
                # 标准字段回退
                return event.get_sender_id()
            except AttributeError:
                # 终极保底方案
                return f"{hash(str(event))}-{time.time()}"

    def _split_into_pages(self, header, result_lines, footer):
        """智能分页逻辑"""
        pages = []
        current_page = []
        current_length = 0
        
        # 计算基础长度
        header_footer = '\n'.join(header + footer)
        base_length = len(header_footer) + 2  # 换行符
        max_content_length = 1000 - base_length

        for line in result_lines:
            line_length = len(line) + 1  # 包含换行符
            
            # 强制分页条件
            if current_length + line_length > max_content_length:
                # 寻找最后一个m3u8链接
                split_index = None
                for i in reversed(range(len(current_page))):
                    if 'm3u8' in current_page[i].lower():
                        split_index = i + 1
                        break
                
                # 如果找不到则强制分割
                if split_index is None:
                    split_index = len(current_page)
                
                # 生成分页
                pages.append('\n'.join(header + current_page[:split_index] + footer))
                current_page = current_page[split_index:]
                current_length = sum(len(line)+1 for line in current_page)
            
            current_page.append(line)
            current_length += line_length

        # 处理剩余内容
        if current_page:
            # 强制确保最后一行为m3u8
            last_m3u8 = None
            for i in reversed(range(len(current_page))):
                if 'm3u8' in current_page[i].lower():
                    last_m3u8 = i + 1
                    break
            
            if last_m3u8 is not None:
                valid_page = current_page[:last_m3u8]
                remaining = current_page[last_m3u8:]
            else:
                valid_page = current_page
                remaining = []

            if valid_page:
                pages.append('\n'.join(header + valid_page + footer))
            if remaining:
                pages.append('\n'.join(header + remaining + footer))

        return pages or ['\n'.join(header + footer)]

    async def _common_handler(self, event, api_urls, keyword):
        """核心处理逻辑"""
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

        # 分页处理
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
        
        return self._split_into_pages(header, result_lines, footer) if result_lines else [
            f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源"
        ]

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
        
        pages = await self._common_handler(event, self.api_url_vod, text)
        session_id = self._get_session_id(event)
        
        self.pagination_cache[session_id] = {
            "pages": pages,
            "timestamp": time.time()
        }
        
        yield event.plain_result(pages[0])
        if len(pages) > 1:
            yield event.plain_result(f"【分页提示】回复2-{len(pages)}查看后续内容（20秒内有效）")

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """成人内容搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞 成人内容服务未启用")
            return
        
        pages = await self._common_handler(event, self.api_url_18, text)
        session_id = self._get_session_id(event)
        
        self.pagination_cache[session_id] = {
            "pages": pages,
            "timestamp": time.time()
        }
        
        yield event.plain_result(pages[0])
        if len(pages) > 1:
            yield event.plain_result(f"【分页提示】回复2-{len(pages)}查看后续内容（20秒内有效）")

    @filter.regex(r"^\d+$")
    async def handle_pagination(self, event: AstrMessageEvent):
        """处理分页请求"""
        session_id = self._get_session_id(event)
        cache = self.pagination_cache.get(session_id)
        
        # 缓存有效性验证
        if not cache or (time.time() - cache["timestamp"]) > 20:
            if session_id in self.pagination_cache:
                del self.pagination_cache[session_id]
            yield event.plain_result("⏳ 分页已过期，请重新搜索")
            return
        
        try:
            page_num = int(event.message_str.strip())
        except ValueError:
            return
        
        pages = cache["pages"]
        if 1 < page_num <= len(pages):
            # 更新缓存时间
            self.pagination_cache[session_id]["timestamp"] = time.time()
            yield event.plain_result(pages[page_num - 1])
        elif page_num == 1:
            yield event.plain_result("📖 已经是第一页啦")
        else:
            yield event.plain_result(f"❌ 无效页码，请输入2-{len(pages)}之间的数字")

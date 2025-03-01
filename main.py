from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time

@register("vod_search", "movie_bot", "影视资源搜索（命令：/vod 电影名）", "2.0.1")
class VodSearchBot(Star):
    _page_cache = {}
    MAX_PAGE_LENGTH = 1000
    CACHE_TIMEOUT = 20

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.api_urls = config.get("api_urls", "").split(',')
        self.max_records = int(config.get("max_records", 15))

    async def _fetch_vod_data(self, keyword):
        """核心搜索逻辑"""
        results = []
        for api_url in self.api_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{api_url.strip()}?ac=videolist&wd={urllib.parse.quote(keyword)}",
                        timeout=15
                    ) as response:
                        if response.status != 200:
                            continue
                        
                        soup = BeautifulSoup(await response.text(), 'xml')
                        for video in soup.select('video')[:self.max_records]:
                            title = video.find('name').text.strip()
                            for dd in video.select('dd'):
                                for url in dd.text.split('#'):
                                    if url := url.strip():
                                        results.append((title, url))
            except Exception as e:
                self.context.logger.error(f"API请求失败：{str(e)}")
        return results

    def _build_pages(self, results):
        """智能分页引擎"""
        pages = []
        current_page = []
        current_length = 0
        last_m3u8 = -1

        # 预生成显示内容
        formatted_lines = []
        for idx, (title, url) in enumerate(results, 1):
            line = f"{idx}. 【{title}】\n   🎬 {url}"
            formatted_lines.append(line)

        # 分页处理
        for line_idx, line in enumerate(formatted_lines):
            line_len = len(line)
            is_m3u8 = line.strip().endswith(".m3u8")

            # 记录最后m3u8位置
            if is_m3u8:
                last_m3u8 = line_idx

            # 超长处理
            if current_length + line_len > self.MAX_PAGE_LENGTH:
                if last_m3u8 != -1 and last_m3u8 >= len(current_page):
                    # 按最近m3u8分页
                    valid_lines = formatted_lines[len(current_page):last_m3u8+1]
                    pages.append(valid_lines)
                    current_page = formatted_lines[last_m3u8+1:line_idx+1]
                    current_length = sum(len(l) for l in current_page)
                    last_m3u8 = -1
                else:
                    # 强制分页
                    pages.append(current_page)
                    current_page = [line]
                    current_length = line_len
                continue

            current_page.append(line)
            current_length += line_len

            # 主动分页点
            if is_m3u8 and current_length > self.MAX_PAGE_LENGTH * 0.8:
                pages.append(current_page)
                current_page = []
                current_length = 0
                last_m3u8 = -1

        # 处理剩余内容
        if current_page:
            pages.append(current_page)

        return pages

    async def _send_pages(self, event, pages):
        """发送分页消息"""
        if not pages:
            yield event.plain_result("🔍 未找到相关资源")
            return

        # 格式化页面
        formatted = []
        for idx, page in enumerate(pages, 1):
            header = [
                f"📺 第 {idx} 页｜共 {len(pages)} 页",
                "━" * 30
            ]
            footer = [
                "━" * 30,
                self._get_page_footer(page),
                f"⏱ 有效期：{self.CACHE_TIMEOUT}秒",
                "💡 回复页码继续浏览"
            ]
            formatted.append("\n".join(header + page + footer))

        # 发送首页
        yield event.plain_result(formatted[0])

        # 缓存多页数据
        if len(formatted) > 1:
            cache_key = f"{event.user_id}_{int(time.time())}"
            self._page_cache[cache_key] = {
                "pages": formatted,
                "expire": time.time() + self.CACHE_TIMEOUT
            }

    def _get_page_footer(self, page):
        """生成页脚信息"""
        last_line = page[-1] if page else ""
        if ".m3u8" in last_line:
            return f"📼 本页以 {last_line.split()[-1]} 结尾"
        
        for line in reversed(page):
            if ".m3u8" in line:
                return f"📼 最近资源：{line.split()[-1]}"
        return "📼 本页无m3u8资源"

    @filter.command("vod")
    async def search_movie(self, event: AstrMessageEvent, text: str):
        # 执行搜索
        results = await self._fetch_vod_data(text)
        if not results:
            yield event.plain_result("🚫 没有找到相关影视资源")
            return

        # 生成分页
        pages = self._build_pages(results)
        async for msg in self._send_pages(event, pages):
            yield msg

    @filter.regex(r"^\d+$")
    async def handle_page(self, event: AstrMessageEvent):
        # 清理过期缓存
        now = time.time()
        expired = [k for k,v in self._page_cache.items() if v["expire"] < now]
        for k in expired:
            del self._page_cache[k]

        # 查找有效缓存
        target_page = int(event.text)
        for cache_key in list(self._page_cache.keys()):
            if cache_key.startswith(f"{event.user_id}_"):
                data = self._page_cache[cache_key]
                if 1 <= target_page <= len(data["pages"]):
                    return event.plain_result(data["pages"][target_page-1])
                else:
                    return event.plain_result(f"⚠️ 请输入1~{len(data['pages'])}之间的数字")
        return MessageEventResult(handled=False)

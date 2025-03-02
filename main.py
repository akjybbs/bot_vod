from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
import asyncio
from astrbot.api.all import *

@register("bot_vod", "appale", "视频搜索及分页功能（命令：/vod /vodd /vodpage）", "1.2")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # API配置
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        # 用户分页数据（user_id: {pages, timestamp, total_pages}）
        self.user_pages = {}
        
    async def _common_handler(self, event, api_urls, keyword):
        """核心搜索逻辑（完整实现）"""
        total_attempts = len(api_urls)
        successful_apis = 0
        grouped_results = {}  # 按标题聚合结果
        ordered_titles = []   # 标题顺序记录
        
        # 遍历所有API源
        for api_url in api_urls:
            api_url = api_url.strip()
            if not api_url:
                continue

            try:
                # 构建请求URL
                encoded_keyword = urllib.parse.quote(keyword)
                query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        if response.status != 200:
                            continue
                            
                        # 解析HTML内容
                        html_content = await response.text()
                        soup = BeautifulSoup(html_content, 'html.parser')
                        video_items = soup.select('rss list video')[:self.records]
                        
                        # 处理每个视频项
                        for item in video_items:
                            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
                            # 提取所有播放链接
                            for dd in item.select('dl > dd'):
                                for url in dd.text.split('#'):
                                    url = url.strip()
                                    if url:
                                        if title not in grouped_results:
                                            grouped_results[title] = []
                                            ordered_titles.append(title)
                                        grouped_results[title].append(url)
                        successful_apis += 1
                        
            except Exception as e:
                self.context.logger.error(f"API请求失败：{str(e)}")
                continue

        # 构建结果列表
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

        # 分页处理逻辑
        pages = []
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
            
            current_start = 0
            while current_start < len(result_lines):
                # 寻找分页点
                possible_ends = [i for i in m3u8_indices if i >= current_start]
                if not possible_ends:
                    break
                
                # 确定最佳分页位置
                best_end = None
                for end in reversed(possible_ends):
                    content_lines = result_lines[current_start:end+1]
                    content_length = sum(len(line) + 1 for line in content_lines)
                    if (len(header_str) + content_length + len(footer_str)) <= 1000:
                        best_end = end
                        break
                if best_end is None:
                    best_end = possible_ends[0]
                
                # 生成分页内容
                page_content = header_str + "\n".join(content_lines) + footer_str
                pages.append(page_content)
                current_start = best_end + 1

            # 存储分页数据
            user_id = event.user_id  # 根据实际接口获取用户ID
            self.user_pages[user_id] = {
                "pages": pages,
                "timestamp": time.time(),
                "total_pages": len(pages),
                "search_info": f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n📊 找到 {total_videos} 条资源"
            }
            # 返回第一页
            yield event.plain_result(pages[0])
        else:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源")

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通视频搜索"""
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

    @filter.command("vodpage")
    async def paginate_results(self, event: AstrMessageEvent, text: str):
        """分页查看结果"""
        user_id = event.user_id
        page_data = self.user_pages.get(user_id)

        # 验证数据有效性
        if not page_data or (time.time() - page_data["timestamp"]) > 300:
            yield event.plain_result("⏳ 搜索结果已过期（有效期5分钟），请重新搜索")
            return

        # 解析页码
        try:
            page_num = int(text.strip())
            if page_num < 1 or page_num > page_data["total_pages"]:
                raise ValueError
        except ValueError:
            yield event.plain_result(f"⚠️ 请输入有效页码（1-{page_data['total_pages']}）")
            return

        # 构建分页消息
        page_content = page_data["pages"][page_num-1]
        new_footer = [
            "━" * 30,
            f"📑 第 {page_num}/{page_data['total_pages']} 页",
            f"⏰ 有效期至 {time.strftime('%H:%M', time.localtime(page_data['timestamp'] + 300))}",
            "━" * 30
        ]
        
        # 替换原有footer
        content_lines = page_content.split("\n")
        content_lines[-6:-3] = new_footer  # 根据实际footer位置调整
        
        yield event.plain_result("\n".join(content_lines))

    async def _clean_expired_records(self):
        """后台清理任务"""
        while True:
            now = time.time()
            expired_users = [
                uid for uid, data in self.user_pages.items()
                if now - data["timestamp"] > 300
            ]
            for uid in expired_users:
                del self.user_pages[uid]
            await asyncio.sleep(60)  # 每分钟检查一次

    async def activate(self):
        """启动插件"""
        await super().activate()
        asyncio.create_task(self._clean_expired_records())

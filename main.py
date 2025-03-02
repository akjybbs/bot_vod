from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
import asyncio
import re

@register("bot_vod", "appale", "视频搜索及分页功能（命令：/vod /vodd /翻页）", "2.0.5")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.user_pages = {}

    def _get_user_identity(self, event: AstrMessageEvent) -> str:
        """用户标识获取（增强版）"""
        try:
            if hasattr(event, 'get_sender_id'):
                return f"{event.platform}-{event.get_sender_id()}"
            return f"{event.platform}-{hash(event)}"
        except Exception as e:
            self.context.logger.error(f"标识获取异常: {str(e)}")
            return "unknown_user"

    async def _common_handler(self, event: AstrMessageEvent, api_urls: list, keyword: str):
        """核心搜索逻辑（智能分页优化版）"""
        user_id = self._get_user_identity(event)
        total_attempts = len(api_urls)
        successful_apis = 0
        grouped_results = {}
        ordered_titles = []

        # API请求处理（保持不变）
        for api_url in api_urls:
            api_url = api_url.strip()
            if not api_url:
                continue

            try:
                encoded_keyword = urllib.parse.quote(keyword)
                query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        if response.status != 200:
                            continue
                            
                        html_content = await response.text()
                        soup = BeautifulSoup(html_content, 'html.parser')
                        video_items = soup.select('rss list video')[:self.records]
                        
                        for item in video_items:
                            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
                            for dd in item.select('dl > dd'):
                                for url in dd.text.split('#'):
                                    if (url := url.strip()):
                                        if title not in grouped_results:
                                            grouped_results[title] = []
                                            ordered_titles.append(title)
                                        grouped_results[title].append({
                                            "url": url,
                                            "is_m3u8": url.endswith('.m3u8')
                                        })
                        successful_apis += 1
                        
            except Exception as e:
                self.context.logger.error(f"API请求错误: {str(e)}")
                continue

        # 构建结构化结果
        structured_results = []
        for idx, title in enumerate(ordered_titles, 1):
            entries = grouped_results.get(title, [])
            structured_results.append({
                "title": f"{idx}. 【{title}】",
                "urls": entries
            })

        # 智能分页处理（关键优化部分）
        pages = []
        if structured_results:
            header = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                f"📊 找到 {sum(len(g['urls']) for g in structured_results)} 条资源",
                "━" * 28
            ]
            
            expiry_time = time.strftime("%H:%M", time.gmtime(time.time() + 300 + 8*3600))
            
            # 分页参数配置
            MAX_PAGE_SIZE = 980    # 最大页面字符数
            MIN_PAGE_CONTENT = 400 # 最小页面内容阈值
            current_page = []
            current_size = len('\n'.join(header))
            pending_blocks = []

            def commit_page():
                """提交当前页并清空缓存"""
                nonlocal current_page, current_size
                if current_page:
                    pages.append('\n'.join(header + current_page))
                    current_page.clear()
                    current_size = len('\n'.join(header))

            for block in structured_results:
                block_lines = [block["title"]] + [f"   🎬 {u['url']}" for u in block["urls"]]
                block_content = '\n'.join(block_lines)
                block_size = len(block_content)
                
                # 智能合并策略
                if current_size + block_size > MAX_PAGE_SIZE:
                    if pending_blocks:  # 优先处理积压的小块
                        current_page.extend(pending_blocks)
                        current_size += sum(len(bl) for bl in pending_blocks) + len(pending_blocks)
                        pending_blocks.clear()
                        commit_page()
                    
                    if block_size > MAX_PAGE_SIZE * 0.7:  # 超大块单独成页
                        commit_page()
                        current_page = block_lines
                        commit_page()
                    else:
                        pending_blocks.extend(block_lines)
                else:
                    # 预测添加后的剩余空间
                    remaining = MAX_PAGE_SIZE - (current_size + block_size)
                    if remaining > MIN_PAGE_CONTENT:
                        current_page.extend(block_lines)
                        current_size += block_size + 1  # +1为换行符
                    else:
                        pending_blocks.extend(block_lines)

            # 处理积压的剩余块
            if pending_blocks:
                if (MAX_PAGE_SIZE - current_size) > len('\n'.join(pending_blocks)):
                    current_page.extend(pending_blocks)
                    commit_page()
                else:
                    commit_page()
                    pages.append('\n'.join(header + pending_blocks))

            # 添加统一页脚
            total_pages = len(pages)
            for page_num in range(total_pages):
                pages[page_num] = self._build_page_footer(
                    content=pages[page_num],
                    page_num=page_num+1,
                    total_pages=total_pages,
                    expiry_time=expiry_time
                )

            # 存储分页数据
            self.user_pages[user_id] = {
                "pages": pages,
                "timestamp": time.time(),
                "total_pages": total_pages,
                "search_info": f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n📊 找到 {sum(len(g['urls']) for g in structured_results)} 条资源"
            }
            yield event.plain_result(pages[0])
        else:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源")

    def _build_page_footer(self, content: str, page_num: int, total_pages: int, expiry_time: str) -> str:
        """构建完整页脚（修复时间显示）"""
        footer = [
            "━" * 28,
            f"📑 第 {page_num}/{total_pages} 页",
            f"⏰ 有效期至 {expiry_time}（北京时间）",
            "💡 播放提示：",
            "1. 移动端直接粘贴链接到浏览器",
            "2. 电脑端推荐使用PotPlayer/VLC播放",
            "3. 使用:/翻页 页码(跳转页面)",
            "━" * 28
        ]
        return content.replace("━" * 28, '\n'.join(footer), 1)

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

    @filter.command("翻页")
    async def paginate_results(self, event: AstrMessageEvent, text: str):
        """分页查看结果（修复时间显示）"""
        user_id = self._get_user_identity(event)
        page_data = self.user_pages.get(user_id)

        if not page_data or (time.time() - page_data["timestamp"]) > 300:
            yield event.plain_result("⏳ 搜索结果已过期（有效期5分钟），请重新搜索")
            return

        try:
            page_num = int(text.strip())
            if not 1 <= page_num <= page_data["total_pages"]:
                raise ValueError
        except ValueError:
            yield event.plain_result(f"⚠️ 请输入有效页码（1-{page_data['total_pages']}）")
            return

        # 更新有效期（单次替换）
        new_expiry = time.strftime("%H:%M", time.gmtime(time.time() + 300 + 8*3600))
        content = page_data["pages"][page_num-1].replace(
            "有效期至", f"有效期至 {new_expiry}", 1
        )
        yield event.plain_result(content)

    async def _clean_expired_records(self):
        """自动清理任务"""
        while True:
            now = time.time()
            expired_users = [uid for uid, data in self.user_pages.items() if now - data["timestamp"] > 300]
            for uid in expired_users:
                del self.user_pages[uid]
            await asyncio.sleep(60)

    async def activate(self):
        """插件激活"""
        await super().activate()
        asyncio.create_task(self._clean_expired_records())

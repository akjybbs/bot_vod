from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
import asyncio
import re

@register("bot_vod", "appale", "视频搜索及分页功能（命令：/vod /vodd /翻页）", "2.0.3")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.user_pages = {}
        self.lock = asyncio.Lock()  # 添加线程安全锁

    def _get_user_identity(self, event: AstrMessageEvent) -> str:
        """增强用户标识获取"""
        try:
            if event.platform == "wechat":
                return f"wechat-{event.user.openid}"
            return f"{event.platform}-{event.get_sender_id()}"
        except Exception as e:
            self.context.logger.error(f"标识获取异常: {str(e)}")
            return f"unknown-{int(time.time())}"

    async def _common_handler(self, event: AstrMessageEvent, api_urls: list, keyword: str):
        """核心搜索逻辑（精确分页控制）"""
        async with self.lock:  # 保证线程安全
            user_id = self._get_user_identity(event)
            total_attempts = len(api_urls)
            successful_apis = 0
            grouped_results = {}
            ordered_titles = []

            # API请求处理
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

            # 智能分页处理（确保标题完整）
            pages = []
            if structured_results:
                header = [
                    f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                    f"📊 找到 {sum(len(g['urls']) for g in structured_results)} 条资源",
                    "━" * 28
                ]
                footer_base = [
                    "━" * 28,
                    "💡 播放提示：",
                    "1. 移动端直接粘贴链接到浏览器",
                    "2. 电脑端推荐使用PotPlayer/VLC播放",
                    "3. 使用:/翻页 页码(跳转页面)",
                    "━" * 28
                ]

                # 生成有效期提示
                expiry_timestamp = time.time() + 300
                beijing_time = time.strftime("%H:%M", time.gmtime(expiry_timestamp + 8 * 3600))
                
                # 预计算基础长度
                header_content = '\n'.join(header)
                header_length = len(header_content) + 1  # 包含换行符
                base_footer = [
                    f"⏰ 有效期至 {beijing_time}（北京时间）",
                    *footer_base
                ]
                footer_content = '\n'.join(base_footer)
                base_footer_length = len(footer_content) + 30  # 预留页码空间

                current_page = []
                current_length = header_length  # 当前内容总长度（含header）
                
                for title_block in structured_results:
                    # 生成标题块内容
                    block_lines = [title_block["title"]]
                    block_lines.extend([f"   🎬 {u['url']}" for u in title_block["urls"]])
                    block_content = '\n'.join(block_lines)
                    block_size = len(block_content) + 2  # 块内容长度（含首尾换行）
                    
                    # 计算预估总长度（当前内容 + 块 + 页脚）
                    estimated_total = current_length + block_size + base_footer_length
                    
                    # 分页判断（保证至少显示一个标题）
                    if estimated_total > 1000 and len(current_page) > 0:
                        # 添加页脚生成当前页
                        page_number = len(pages) + 1
                        footer = [
                            "━" * 28,
                            f"📑 第 {page_number}/PAGES 页",
                            *base_footer
                        ]
                        full_content = '\n'.join([header_content] + current_page + footer)
                        pages.append(full_content)
                        
                        # 重置状态
                        current_page = block_lines
                        current_length = header_length + block_size
                    else:
                        # 追加到当前页
                        if current_page:
                            current_page.append('')  # 添加块间空行
                            current_length += 1
                        current_page.extend(block_lines)
                        current_length += block_size

                # 处理最后一页
                if current_page:
                    page_number = len(pages) + 1
                    footer = [
                        "━" * 28,
                        f"📑 第 {page_number}/PAGES 页",
                        *base_footer
                    ]
                    full_content = '\n'.join([header_content] + current_page + footer)
                    pages.append(full_content)

                # 更新总页数
                total_pages = len(pages)
                for i in range(len(pages)):
                    pages[i] = pages[i].replace("PAGES", str(total_pages))
                    
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
        """精确分页控制"""
        user_id = self._get_user_identity(event)
        async with self.lock:  # 线程安全访问
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

            # 动态更新有效期
            new_expiry = time.time() + 600
            new_beijing_time = time.strftime("%H:%M", time.gmtime(new_expiry + 8 * 3600))
            
            # 正则替换时间
            old_time_pattern = r"⏰ 有效期至 \d{2}:\d{2}"
            updated_content = re.sub(
                old_time_pattern, 
                f"⏰ 有效期至 {new_beijing_time}", 
                page_data["pages"][page_num-1]
            )
            
            # 更新存储时间戳
            self.user_pages[user_id]["timestamp"] = new_expiry - 300  # 保持总有效期不变
            yield event.plain_result(updated_content)

    async def _clean_expired_records(self):
        """自动清理任务"""
        while True:
            async with self.lock:  # 线程安全清理
                now = time.time()
                expired_users = [
                    uid for uid, data in self.user_pages.items()
                    if now - data["timestamp"] > 300
                ]
                for uid in expired_users:
                    del self.user_pages[uid]
            await asyncio.sleep(60)

    async def activate(self):
        """插件激活"""
        await super().activate()
        asyncio.create_task(self._clean_expired_records())

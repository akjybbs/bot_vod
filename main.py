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
        self.lock = asyncio.Lock()

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
        """核心搜索逻辑（智能分页优化版）"""
        async with self.lock:
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

            # 智能分页处理（动态合并优化）
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

                # 有效期计算
                expiry_timestamp = time.time() + 300
                beijing_time = time.strftime("%H:%M", time.gmtime(expiry_timestamp + 8 * 3600))
                
                # 基础长度计算
                header_content = '\n'.join(header)
                header_length = len(header_content) + 1  # 包含换行符
                base_footer = [
                    f"⏰ 有效期至 {beijing_time}（北京时间）",
                    *footer_base
                ]
                footer_content = '\n'.join(base_footer)
                base_footer_length = len(footer_content) + 30  # 预留页码空间

                current_blocks = []
                remaining_blocks = structured_results.copy()
                min_page_size = 200  # 最小页面内容阈值

                while remaining_blocks:
                    # 初始化当前页
                    current_page = []
                    current_length = header_length
                    page_filled = False
                    
                    # 动态填充策略
                    while remaining_blocks and not page_filled:
                        next_block = remaining_blocks[0]
                        
                        # 生成块内容
                        block_lines = [next_block["title"]]
                        block_lines.extend([f"   🎬 {u['url']}" for u in next_block["urls"]])
                        block_content = '\n'.join(block_lines)
                        
                        # 计算块尺寸
                        block_size = len(block_content) + (1 if current_page else 0)  # 块间换行
                        estimated_total = current_length + block_size + base_footer_length
                        
                        # 填充条件判断
                        if (current_length + block_size + base_footer_length <= 1200) or \
                           (not current_page and estimated_total <= 1500):
                            # 添加块到当前页
                            if current_page:
                                current_page.append('')  # 块间空行
                            current_page.extend(block_lines)
                            current_length += block_size
                            remaining_blocks.pop(0)
                            
                            # 检查后续小块是否可以合并
                            lookahead_blocks = 3  # 预看后续3个块
                            for _ in range(min(lookahead_blocks, len(remaining_blocks))):
                                test_block = remaining_blocks[0]
                                test_lines = [test_block["title"]] + [f"   🎬 {u['url']}" for u in test_block["urls"]]
                                test_size = len('\n'.join(test_lines)) + 1  # 换行符
                                
                                if current_length + test_size + base_footer_length <= 1000:
                                    current_page.append('')
                                    current_page.extend(test_lines)
                                    current_length += test_size
                                    remaining_blocks.pop(0)
                                else:
                                    break
                        else:
                            page_filled = True

                    # 生成页面内容
                    if current_page:
                        # 检查页面内容是否过小
                        if len('\n'.join(current_page)) < min_page_size and remaining_blocks:
                            # 尝试合并下一个块
                            next_block = remaining_blocks[0]
                            test_lines = [next_block["title"]] + [f"   🎬 {u['url']}" for u in next_block["urls"]]
                            test_size = len('\n'.join(test_lines)) + 1
                            
                            if current_length + test_size + base_footer_length <= 1500:
                                current_page.append('')
                                current_page.extend(test_lines)
                                current_length += test_size
                                remaining_blocks.pop(0)

                        # 构建页脚
                        page_number = len(pages) + 1
                        footer = [
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
        """智能分页控制"""
        user_id = self._get_user_identity(event)
        async with self.lock:
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
            new_expiry = time.time() + 300
            new_beijing_time = time.strftime("%H:%M", time.gmtime(new_expiry + 8 * 3600))
            
            # 使用正则精确替换时间
            old_time_pattern = r"⏰ 有效期至 \d{2}:\d{2}"
            updated_content = re.sub(
                old_time_pattern, 
                f"⏰ 有效期至 {new_beijing_time}", 
                page_data["pages"][page_num-1]
            )
            
            # 保持总有效期不变
            self.user_pages[user_id]["timestamp"] = new_expiry - 300
            yield event.plain_result(updated_content)

    async def _clean_expired_records(self):
        """自动清理任务"""
        while True:
            async with self.lock:
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

from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
import asyncio
import re

@register("bot_vod", "appale", "视频搜索及分页功能（命令：/vod /vodd /vodpage）", "2.0.2")
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
            if hasattr(event, 'get_sender_id') and callable(event.get_sender_id):
                return event.get_sender_id()
            elif hasattr(event, 'user') and hasattr(event.user, 'openid'):
                return f"wechat-{event.user.openid}"
            return f"{event.platform}-{hash(event)}"
        except Exception as e:
            self.context.logger.error(f"标识获取异常: {str(e)}")
            return "unknown_user"

    async def _common_handler(self, event: AstrMessageEvent, api_urls: list, keyword: str):
        """核心搜索逻辑（精确分页控制）"""
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

        # 智能分页处理（精确控制）
        pages = []
        if structured_results:
            header = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                f"📊 找到 {sum(len(g['urls']) for g in structured_results)} 条资源",
                "━" * 25
            ]
            footer_base = [
                "━" * 25,
                "💡 播放提示：",
                "1. 移动端直接粘贴链接到浏览器",
                "2. 电脑端推荐使用PotPlayer/VLC播放",
                "3. /vodpage 页码(跳转页面)",
                "━" * 25
            ]

            # 单标题特殊处理
            if len(structured_results) == 1:
                page_content = [header[0], header[1], header[2]]
                title_block = structured_results[0]
                page_content.append(title_block["title"])
                for url_info in title_block["urls"]:
                    page_content.append(f"   🎬 {url_info['url']}")
                page_content.extend(footer_base)
                pages.append('\n'.join(page_content))
            else:
                # 多标题分页逻辑
                current_page = []
                current_length = len('\n'.join(header)) + 1
                current_titles = 0
                last_m3u8_index = -1

                def finalize_page():
                    nonlocal current_page, last_m3u8_index
                    if last_m3u8_index != -1:
                        # 找到最近的m3u8分页点
                        split_index = last_m3u8_index + 1
                        final_content = current_page[:split_index]
                        remaining_content = current_page[split_index:]
                    else:
                        # 没有m3u8时按内容分割
                        final_content = current_page
                        remaining_content = []

                    # 构建页脚
                    page_footer = [
                        "━" * 25,
                        f"📑 第 {len(pages)+1}/PAGES 页。  /vodpage 页码(跳转页面)",
                        f"⏰ 有效期至 {time.strftime('%H:%M', time.localtime(time.time() + 300))}",
                        *footer_base
                    ]
                    
                    full_content = '\n'.join(header + final_content + page_footer)
                    pages.append(full_content)
                    
                    # 重置状态
                    current_page = remaining_content
                    current_length = len('\n'.join(header)) + len('\n'.join(current_page)) + 1
                    last_m3u8_index = -1
                    return len(remaining_content) > 0

                for title_block in structured_results:
                    title_line = title_block["title"]
                    url_lines = [f"   🎬 {u['url']}" for u in title_block["urls"]]
                    
                    # 检测是否需要强制分页
                    block_content = [title_line] + url_lines
                    block_length = len('\n'.join(block_content))
                    
                    # 添加标题前的检查
                    if current_titles >= 2 and current_length + block_length > 1000:
                        while finalize_page():
                            continue
                        
                    current_page.append(title_line)
                    current_length += len(title_line) + 1
                    current_titles += 1
                    
                    for i, url_line in enumerate(url_lines):
                        line_length = len(url_line) + 1
                        # 记录m3u8位置
                        if title_block["urls"][i]["is_m3u8"]:
                            last_m3u8_index = len(current_page)
                        
                        # 检查长度限制
                        if current_length + line_length > 1000:
                            if finalize_page():
                                current_page.append(url_line)
                                current_length += line_length
                            else:
                                current_page.append(url_line)
                                current_length = len('\n'.join(header)) + line_length + 1
                        else:
                            current_page.append(url_line)
                            current_length += line_length
                
                # 处理剩余内容
                while len(current_page) > 0:
                    finalize_page()

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

    @filter.command("vodpage")
    async def paginate_results(self, event: AstrMessageEvent, text: str):
        """分页查看结果（精确控制）"""
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

        # 动态更新有效期
        content = page_data["pages"][page_num-1].replace(
            time.strftime('%H:%M', time.localtime(page_data['timestamp'] + 300)),
            time.strftime('%H:%M', time.localtime(time.time() + 300))
        )
        yield event.plain_result(content)

    async def _clean_expired_records(self):
        """自动清理任务"""
        while True:
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

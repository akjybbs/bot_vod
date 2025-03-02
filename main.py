from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
import asyncio
import re
import random

@register("bot_vod", "appale", "视频搜索及分页功能（命令：/vod /vodd /翻页）", "3.0.0")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.user_pages = {}
        self.MAX_PAGE_LENGTH = 1000
        self.REQUEST_TIMEOUT = 15
        self.MAX_RETRIES = 2

    def _get_user_identity(self, event: AstrMessageEvent) -> str:
        """生成唯一用户标识"""
        try:
            return f"{event.platform}-{event.get_sender_id()}" if hasattr(event, 'get_sender_id') else f"{event.platform}-{hash(event)}"
        except Exception as e:
            self.context.logger.error(f"用户标识生成失败: {str(e)}")
            return f"unknown-{int(time.time())}"

    async def _fetch_api(self, url: str, keyword: str, is_adult: bool = False) -> dict:
        """执行API请求（完整实现）"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": urllib.parse.urlparse(url).scheme + "://" + urllib.parse.urlparse(url).netloc + "/"
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url=url,
                        params={"wd": keyword} if not is_adult else {"q": keyword},
                        headers=headers,
                        timeout=self.REQUEST_TIMEOUT,
                        proxy=self.config.get("proxy") if not is_adult else None
                    ) as response:
                        if response.status != 200:
                            continue

                        content = await response.text()
                        soup = BeautifulSoup(content, 'html.parser')

                        # 解析正常资源
                        if not is_adult:
                            items = soup.select('div.module-search-item')
                            return {
                                "success": True,
                                "data": [{
                                    "title": item.select_one('div.video-info-header a').get_text(strip=True),
                                    "urls": [{
                                        "url": a['href'],
                                        "name": a.get_text(strip=True)
                                    } for a in item.select('div.module-item-cover a')[:self.records]]
                                } for item in items]
                            }
                        # 解析特殊资源
                        else:
                            items = soup.select('div.tg-item')
                            return {
                                "success": True,
                                "data": [{
                                    "title": item.select_one('div.tg-info').get_text(strip=True),
                                    "urls": [{
                                        "url": item.select_one('a')['href'],
                                        "name": item.select_one('img')['alt'].strip()
                                    }][:self.records]
                                } for item in items]
                            }
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.context.logger.warning(f"API请求失败（尝试{attempt+1}）: {str(e)}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(1 + random.random())
        return {"success": False}

    def _build_content_blocks(self, results: list) -> list:
        """构建分页内容块（完整实现）"""
        blocks = []
        for result in results:
            title = f"🔍 {result['title']}"
            urls = [f"   🎬 {url['url']} ({url['name']})" for url in result['urls']]
            
            # 计算块总长度（包含换行符）
            block_lines = [title] + urls
            total_length = sum(len(line) + 1 for line in block_lines) - 1  # 最后一行不加换行符
            
            blocks.append({
                "type": "resource_block",
                "lines": block_lines,
                "length": total_length,
                "title": title,
                "url_count": len(urls)
            })
        return blocks

    def _generate_pages(self, header: list, blocks: list) -> list:
        """分页生成器（完整算法）"""
        pages = []
        current_page = []
        current_length = sum(len(line) + 1 for line in header)  # 页眉长度
        
        # 页脚模板
        footer_template = [
            "━" * 30,
            "📖 第 {current_page}/{total_pages} 页",
            "⏳ 有效期至 {expire_time}（北京时间）",
            "🔧 使用 /翻页 [页码] 切换页面",
            "━" * 30
        ]
        footer_length = sum(len(line.format(current_page=1, total_pages=1, expire_time="00:00")) + 1 for line in footer_template) - 1
        
        for block in blocks:
            required_space = block['length'] + 2  # 块前后空行
            test_length = current_length + required_space + footer_length
            
            # 情况1：可以完整放入当前页
            if test_length <= self.MAX_PAGE_LENGTH:
                current_page.append(block)
                current_length += required_space
                continue
                
            # 情况2：需要新建页面
            if current_page:
                # 生成实际页面内容
                page_content = []
                for blk in current_page:
                    page_content.extend(blk['lines'])
                    page_content.append('')  # 块间空行
                page_content.pop()  # 移除最后空行
                
                # 生成完整页面
                expire_time = time.strftime("%H:%M", time.localtime(time.time() + 300 + 8*3600))
                footer = [line.format(
                    current_page=len(pages)+1,
                    total_pages="TBD",
                    expire_time=expire_time
                ) for line in footer_template]
                
                full_page = '\n'.join(header + page_content + footer)
                pages.append(full_page)
                current_page = []
                current_length = sum(len(line) + 1 for line in header)
                
            # 处理超大块（单独成页）
            test_length = sum(len(line) + 1 for line in header) + block['length'] + footer_length
            if test_length > self.MAX_PAGE_LENGTH:
                # 执行截断处理
                truncated_lines = [block['title'], "   ⚠️ 部分结果已折叠（完整列表请访问网站）"]
                for url_line in block['lines'][1:]:
                    if sum(len(line) + 1 for line in truncated_lines) + footer_length + 50 < self.MAX_PAGE_LENGTH:
                        truncated_lines.append(url_line)
                current_page = [{
                    "type": "truncated_block",
                    "lines": truncated_lines,
                    "length": sum(len(line) + 1 for line in truncated_lines) - 1
                }]
            else:
                current_page.append(block)
            current_length = sum(len(line) + 1 for line in header) + current_page[0]['length'] + 2
        
        # 处理最后一页
        if current_page:
            page_content = []
            for blk in current_page:
                page_content.extend(blk['lines'])
                page_content.append('')
            page_content.pop()
            
            expire_time = time.strftime("%H:%M", time.localtime(time.time() + 300 + 8*3600))
            footer = [line.format(
                current_page=len(pages)+1,
                total_pages="TBD",
                expire_time=expire_time
            ) for line in footer_template]
            
            full_page = '\n'.join(header + page_content + footer)
            pages.append(full_page)
        
        # 更新总页数
        for idx in range(len(pages)):
            pages[idx] = pages[idx].replace("TBD", str(len(pages)))
        
        return pages

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通资源搜索（完整实现）"""
        keyword = text.strip()
        if not keyword:
            yield event.plain_result("🔍 请输入搜索关键词，例如：/vod 流浪地球")
            return
        
        results = []
        total_apis = len(self.api_url_vod)
        successful_apis = 0
        
        async with event.loading("🔍 搜索中..."):
            for api_url in self.api_url_vod:
                try:
                    response = await self._fetch_api(api_url, keyword)
                    if response['success'] and response['data']:
                        results.extend(response['data'])
                        successful_apis += 1
                except Exception as e:
                    self.context.logger.error(f"API处理失败：{str(e)}")
        
        if results:
            header = [
                f"🔍 搜索 {total_apis} 个源｜成功 {successful_apis} 个",
                f"📚 找到 {sum(len(res['urls']) for res in results)} 条资源",
                "━" * 30
            ]
            
            # 构建分页
            blocks = self._build_content_blocks(results)
            pages = self._generate_pages(header, blocks)
            
            # 存储分页状态
            user_id = self._get_user_identity(event)
            self.user_pages[user_id] = {
                "pages": pages,
                "timestamp": time.time(),
                "total_pages": len(pages),
                "search_type": "normal"
            }
            
            yield event.plain_result(pages[0])
        else:
            yield event.plain_result(f"⚠️ 未找到【{keyword}】相关资源\n尝试更换关键词或稍后重试")

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """特殊资源搜索（完整实现）"""
        if not self.config.get("enable_adult"):
            yield event.plain_result("⛔ 此功能暂未开放")
            return
        
        keyword = text.strip()
        if not keyword:
            yield event.plain_result("🔞 请输入搜索关键词")
            return
        
        results = []
        successful_apis = 0
        
        async with event.loading("🔍 特殊搜索中..."):
            for api_url in self.api_url_18:
                try:
                    response = await self._fetch_api(api_url, keyword, is_adult=True)
                    if response['success'] and response['data']:
                        results.extend(response['data'])
                        successful_apis += 1
                except Exception as e:
                    self.context.logger.error(f"特殊API失败：{str(e)}")
        
        if results:
            header = [
                f"🔞 搜索 {len(self.api_url_18)} 个源｜成功 {successful_apis} 个",
                f"📚 找到 {sum(len(res['urls']) for res in results)} 条特殊资源",
                "⚠️ 本结果保留5分钟",
                "━" * 30
            ]
            
            blocks = self._build_content_blocks(results)
            pages = self._generate_pages(header, blocks)
            
            user_id = self._get_user_identity(event)
            self.user_pages[user_id] = {
                "pages": pages,
                "timestamp": time.time(),
                "total_pages": len(pages),
                "search_type": "adult"
            }
            
            yield event.plain_result(pages[0])
        else:
            yield event.plain_result(f"⚠️ 未找到【{keyword}】相关特殊资源")

    @filter.command("翻页")
    async def paginate(self, event: AstrMessageEvent, text: str):
        """分页处理（完整实现）"""
        user_id = self._get_user_identity(event)
        page_data = self.user_pages.get(user_id)
        
        # 有效性检查
        if not page_data or time.time() - page_data['timestamp'] > 300:
            yield event.plain_result("⏳ 搜索结果已过期，请重新搜索")
            return
        
        # 智能页码解析
        text = text.strip().lower()
        cn_num_map = {'一':1, '二':2, '三':3, '四':4, '五':5, '末': page_data['total_pages']}
        match = re.match(r"^(?:第|p)?(\d+|[\u4e00-\u9fa5]{1,3})[页]?$", text)
        
        page_num = 0
        if match:
            raw = match.group(1)
            if raw in cn_num_map:
                page_num = cn_num_map[raw]
            else:
                try:
                    page_num = int(raw)
                except:
                    pass
        else:
            try:
                page_num = int(text)
            except:
                pass
        
        # 边界检查
        if not 1 <= page_num <= page_data['total_pages']:
            help_msg = [
                f"⚠️ 无效页码（1-{page_data['total_pages']}）",
                "支持格式：",
                "· 数字：2",
                "· 中文：二",
                "· 带页码：第3页",
                f"当前共 {page_data['total_pages']} 页"
            ]
            yield event.plain_result('\n'.join(help_msg))
            return
        
        # 更新有效期
        new_expire = time.time() + 300
        new_time_str = time.strftime("%H:%M", time.localtime(new_expire + 8*3600))
        updated_page = re.sub(
            r'有效期至 \d{2}:\d{2}',
            f'有效期至 {new_time_str}',
            page_data['pages'][page_num-1]
        )
        
        # 更新存储时间
        self.user_pages[user_id]['timestamp'] = new_expire - 300
        
        yield event.plain_result(updated_page)

    async def _cleanup_task(self):
        """定时清理任务（完整实现）"""
        while True:
            now = time.time()
            to_remove = []
            
            for user_id, data in self.user_pages.items():
                if now - data['timestamp'] > 300 or data['total_pages'] > 50:
                    to_remove.append(user_id)
            
            for user_id in to_remove:
                del self.user_pages[user_id]
                self.context.logger.info(f"清理用户分页数据：{user_id}")
            
            await asyncio.sleep(60)

    async def activate(self):
        """激活插件（完整实现）"""
        await super().activate()
        asyncio.create_task(self._cleanup_task())

from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
import asyncio
import re

@register("bot_vod", "appale", "视频搜索及分页功能（命令：/vod /vodd /翻页）", "2.1.0")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.user_pages = {}
        self.MAX_PAGE_LENGTH = 1000  # 严格限制单页长度

    def _get_user_identity(self, event: AstrMessageEvent) -> str:
        """用户身份标识"""
        try:
            if hasattr(event, 'get_sender_id') and callable(event.get_sender_id):
                return f"{event.platform}-{event.get_sender_id()}"
            return f"{event.platform}-{hash(event)}"
        except Exception as e:
            self.context.logger.error(f"用户标识获取失败: {str(e)}")
            return "unknown"

    def _create_content_blocks(self, structured_results):
        """构建不可分割的内容块"""
        blocks = []
        for result in structured_results:
            title = result["title"]
            urls = [f"   🎬 {url['url']}" for url in result["urls"]]
            
            # 计算块尺寸（包含所有换行符）
            block_content = [title] + urls
            total_length = sum(len(line) + 1 for line in block_content)  # 每行加换行符
            total_length -= 1  # 最后一个换行符不计入
            
            blocks.append({
                "title": title,
                "content": block_content,
                "length": total_length
            })
        return blocks

    def _build_pages(self, header, blocks):
        """智能分页核心算法"""
        pages = []
        current_page = []
        header_length = sum(len(line) + 1 for line in header)  # 页头固定长度
        
        # 基础页脚模板
        base_footer = [
            "━" * 28,
            "📑 第 {current}/{total} 页",
            "⏰ 有效期至 {time}（北京时间）",
            "💡 使用 /翻页 页码 切换页面",
            "━" * 28
        ]
        footer_template = '\n'.join(base_footer)
        
        for block in blocks:
            # 预计算页脚长度
            temp_footer = footer_template.format(
                current=len(pages)+1,
                total="N",
                time="00:00"
            )
            estimated_footer_length = len(temp_footer)
            
            # 计算当前页总长度
            current_content = []
            if current_page:
                current_content = [line for b in current_page for line in b["content"]]
            proposed_content = current_content + block["content"]
            
            proposed_page = '\n'.join(header + proposed_content + [temp_footer])
            proposed_length = len(proposed_page)
            
            # 情况1：可以完整加入当前页
            if proposed_length <= self.MAX_PAGE_LENGTH:
                current_page.append(block)
                continue
                
            # 情况2：需要新建页面
            if current_page:
                # 生成实际页脚
                expiry_time = time.strftime("%H:%M", time.gmtime(time.time() + 300 + 8*3600))
                actual_footer = footer_template.format(
                    current=len(pages)+1,
                    total="N",
                    time=expiry_time
                )
                
                # 生成完整页面内容
                page_content = [line for b in current_page for line in b["content"]]
                full_page = '\n'.join(header + page_content + [actual_footer])
                
                # 长度二次校验
                while len(full_page) > self.MAX_PAGE_LENGTH:
                    # 移除最后一个块（极端情况处理）
                    removed_block = current_page.pop()
                    page_content = [line for b in current_page for line in b["content"]]
                    full_page = '\n'.join(header + page_content + [actual_footer])
                
                pages.append(full_page)
                current_page = []
            
            # 处理当前块（可能超长）
            block_page = '\n'.join(header + block["content"] + [temp_footer])
            if len(block_page) > self.MAX_PAGE_LENGTH:
                # 超长块特殊处理：截断URL但保留标题
                truncated_content = [block["title"], "   （资源过多，已自动截断）"]
                remain_length = self.MAX_PAGE_LENGTH - len('\n'.join(header + truncated_content + [temp_footer]))
                
                current_length = sum(len(line)+1 for line in truncated_content)
                for url in block["content"][1:]:  # 跳过标题
                    url_length = len(url) + 1
                    if current_length + url_length > remain_length:
                        break
                    truncated_content.append(url)
                    current_length += url_length
                
                # 构建有效页
                expiry_time = time.strftime("%H:%M", time.gmtime(time.time() + 300 + 8*3600))
                actual_footer = footer_template.format(
                    current=len(pages)+1,
                    total="N",
                    time=expiry_time
                )
                full_page = '\n'.join(header + truncated_content + [actual_footer])
                pages.append(full_page)
            else:
                current_page.append(block)
        
        # 处理最后一页
        if current_page:
            expiry_time = time.strftime("%H:%M", time.gmtime(time.time() + 300 + 8*3600))
            page_content = [line for b in current_page for line in b["content"]]
            actual_footer = footer_template.format(
                current=len(pages)+1,
                total="N",
                time=expiry_time
            )
            full_page = '\n'.join(header + page_content + [actual_footer])
            pages.append(full_page)
        
        # 更新总页数
        total_pages = len(pages)
        for i in range(len(pages)):
            pages[i] = pages[i].replace("total=\"N\"", f"total={total_pages}").replace(" total=N", f" {total_pages}")
        
        return pages

    async def _common_handler(self, event: AstrMessageEvent, api_urls: list, keyword: str):
        # ... [保持原有的API请求处理逻辑，生成structured_results] ...

        if structured_results:
            header = [
                f"🔍 搜索 {len(api_urls)} 个源｜成功 {successful_apis} 个",
                f"📊 找到 {sum(len(r['urls']) for r in structured_results)} 条资源",
                "━" * 28
            ]
            
            # 构建内容块并分页
            blocks = self._create_content_blocks(structured_results)
            pages = self._build_pages(header, blocks)
            
            # 存储分页数据
            user_id = self._get_user_identity(event)
            self.user_pages[user_id] = {
                "pages": pages,
                "timestamp": time.time(),
                "total_pages": len(pages)
            }
            
            yield event.plain_result(pages[0])
        else:
            yield event.plain_result("⚠️ 未找到相关资源")

    @filter.command("翻页")
    async def paginate_results(self, event: AstrMessageEvent, text: str):
        """智能翻页处理"""
        user_id = self._get_user_identity(event)
        page_data = self.user_pages.get(user_id)

        # 有效性检查
        if not page_data or (time.time() - page_data["timestamp"]) > 300:
            yield event.plain_result("⏳ 搜索结果已过期，请重新搜索")
            return

        # 增强版页码解析
        text = text.strip().lower()
        cn_num_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '首': 1, '首页': 1, '末': page_data["total_pages"], '尾页': page_data["total_pages"]
        }
        
        # 匹配多种格式：第2页、page3、直接数字等
        match = re.match(r"^(?:第|page)?(\d+|[\u4e00-\u9fa5]+)[页]?$", text)
        if match:
            raw_num = match.group(1)
            if raw_num in cn_num_map:
                page_num = cn_num_map[raw_num]
            else:
                try:
                    page_num = int(raw_num)
                except ValueError:
                    page_num = 0
        else:
            try:
                page_num = int(re.sub(r"\D", "", text))
            except:
                page_num = 0

        # 边界检查
        if not 1 <= page_num <= page_data["total_pages"]:
            yield event.plain_result(
                f"⚠️ 无效页码\n"
                f"当前共 {page_data['total_pages']} 页\n"
                f"支持格式：\n"
                f"· 数字（2）\n"
                f"· 中文（二）\n"
                f"· 第X页"
            )
            return

        # 更新有效期
        new_expiry = time.time() + 300
        new_time = time.strftime("%H:%M", time.gmtime(new_expiry + 8*3600))
        updated_page = re.sub(
            r"有效期至 \d{2}:\d{2}",
            f"有效期至 {new_time}",
            page_data["pages"][page_num-1]
        )
        
        # 更新时间戳但保持页面内容不变
        self.user_pages[user_id]["timestamp"] = new_expiry - 300
        
        yield event.plain_result(updated_page)

    async def _clean_expired_records(self):
        """内存保护机制"""
        while True:
            now = time.time()
            expired = []
            
            for user_id, data in self.user_pages.items():
                # 清理超过5分钟或超过50页的记录
                if (now - data["timestamp"] > 300) or (data["total_pages"] > 50):
                    expired.append(user_id)
            
            for user_id in expired:
                del self.user_pages[user_id]
                self.context.logger.info(f"清理用户记录: {user_id}")
            
            await asyncio.sleep(60)

    async def activate(self):
        """激活插件"""
        await super().activate()
        asyncio.create_task(self._clean_expired_records())

from astrbot.api.all import *
from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import time
from typing import Dict, List
from typing import Dict
from astrbot.api.all import *
import asyncio
import time
import subprocess
import os
import json
import requests

# 用户状态跟踪（支持多用户并发）
VOD_STATES: Dict[int, Dict[str, float]] = {}

@register("bot_vod", "appale", "影视搜索（命令：/vod 或 /vodd + 关键词）", "3.0")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))
        self.page_size = 5  # 每页显示条目数
        self.timeout = 20  # 超时时间（秒）

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视搜索"""
        if not self.api_url_vod:
            yield event.plain_result("⚠️ 普通视频服务未启用")
            return
        async for msg in self._process_search(event, self.api_url_vod, text, "normal"):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """🔞内容搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞成人内容服务未启用")
            return
        async for msg in self._process_search(event, self.api_url_18, text, "adult"):
            yield msg

    async def _process_search(self, event, api_urls, keyword, search_type):
        """处理搜索流程"""
        user_id = event.get_sender_id()
        
        # 检查现有状态
        if user_id in VOD_STATES:
            yield event.plain_result("💤 正在处理您的上一个请求，请稍候...")
            return

        # 开始搜索
        VOD_STATES[user_id] = {
            "state": "searching",
            "timestamp": time.time()
        }
        
        try:
            result = await self._fetch_results(api_urls, keyword)
            if not result:
                yield event.plain_result(f"🔍 没有找到与【{keyword}】相关的内容")
                return

            # 生成分页数据
            pages = self._generate_pages(result)
            if not pages:
                yield event.plain_result("⚠️ 搜索结果格式错误")
                return

            # 更新用户状态
            VOD_STATES[user_id] = {
                "state": "waiting_page",
                "pages": pages,
                "current_page": 0,
                "keyword": keyword,
                "search_type": search_type,
                "timestamp": time.time()
            }

            # 发送第一页
            yield from self._send_page(event, pages[0], 1, len(pages))

        except Exception as e:
            self.context.logger.error(f"搜索出错: {str(e)}")
            yield event.plain_result("⚠️ 搜索服务暂时不可用")
        finally:
            if user_id in VOD_STATES and VOD_STATES[user_id]["state"] == "searching":
                del VOD_STATES[user_id]

    async def _fetch_results(self, api_urls, keyword):
        """获取API结果"""
        results = []
        for api_url in api_urls:
            api_url = api_url.strip()
            if not api_url:
                continue

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{api_url}?ac=videolist&wd={urllib.parse.quote(keyword)}",
                        timeout=15
                    ) as response:
                        if response.status != 200:
                            continue

                        content = await response.text()
                        soup = BeautifulSoup(content, 'html.parser')
                        for item in soup.select('rss list video')[:self.records]:
                            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
                            urls = []
                            for dd in item.select('dl > dd'):
                                urls.extend([url.strip() for url in dd.text.split('#') if url.strip()])
                            if urls:
                                results.append({"title": title, "urls": urls})
            except Exception as e:
                self.context.logger.error(f"API请求失败: {api_url} - {str(e)}")

        return results

    def _generate_pages(self, results):
        """生成分页数据"""
        pages = []
        current_page = []
        current_count = 0

        # 页眉
        header = [
            "🔍 影视搜索结果",
            "━" * 20
        ]

        # 页脚
        footer = [
            "━" * 20,
            "💡 输入数字跳转页面（20秒有效）",
            "💡 输入0取消搜索"
        ]

        for item in results:
            entry = [
                f"🎬 {item['title']}",
                *[f"   → {url}" for url in item['urls']]
            ]

            # 检查是否需要分页
            if current_count + len(entry) + 4 > self.page_size:  # +4为页眉页脚行数
                pages.append(header + current_page + footer)
                current_page = []
                current_count = 0

            current_page.extend(entry)
            current_count += len(entry)

        if current_page:
            pages.append(header + current_page + footer)
        return pages

    async def _send_page(self, event, page_content, current, total):
        """发送分页内容"""
        # 添加页码信息
        content = [f"📑 第 {current}/{total} 页"] + page_content
        yield event.plain_result("\n".join(content))

    @filter.message_handle
    async def handle_interaction(self, event: AstrMessageEvent):
        """处理用户交互"""
        user_id = event.get_sender_id()
        message = event.message_str.strip()
        current_time = time.time()

        # 清理过期状态
        self._clean_expired_states()

        if user_id not in VOD_STATES:
            return MessageEventResult.IGNORE

        state = VOD_STATES[user_id]
        if current_time - state["timestamp"] > self.timeout:
            del VOD_STATES[user_id]
            yield event.plain_result("⏳ 操作已超时，请重新搜索")
            return MessageEventResult.HANDLED

        # 处理页码输入
        if message.isdigit():
            page_num = int(message)
            if page_num == 0:
                del VOD_STATES[user_id]
                yield event.plain_result("🗑 已取消当前搜索")
                return MessageEventResult.HANDLED

            total_pages = len(state["pages"])
            if 1 <= page_num <= total_pages:
                # 更新状态
                state["current_page"] = page_num - 1
                state["timestamp"] = current_time
                # 发送新页面
                yield from self._send_page(
                    event,
                    state["pages"][page_num-1],
                    page_num,
                    total_pages
                )
            else:
                yield event.plain_result(f"⚠️ 请输入1~{total_pages}之间的有效页码")
            return MessageEventResult.HANDLED

        # 处理非数字输入
        yield event.plain_result("⚠️ 请输入数字页码或发送0取消")
        return MessageEventResult.HANDLED

    def _clean_expired_states(self):
        """清理过期状态"""
        current_time = time.time()
        expired = [uid for uid, s in VOD_STATES.items() 
                  if current_time - s["timestamp"] > self.timeout]
        for uid in expired:
            del VOD_STATES[uid]

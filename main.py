from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from typing import AsyncGenerator

MAX_RESULT_LINES = 25  # 结果最大行数控制

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.2")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self._init_config(config)
        self.session = None  # 延迟创建Session

    def _init_config(self, config):
        """配置初始化与校验"""
        # API源处理
        self.api_url_vod = [url.strip() for url in config.get("api_url_vod", "").split(',') if url.strip()]
        self.api_url_18 = [url.strip() for url in config.get("api_url_18", "").split(',') if url.strip()]
        
        # 结果数量控制
        self.records = max(1, int(config.get("records", 3)))
        
        # 超时设置
        self.timeout = aiohttp.ClientTimeout(total=20)

    async def __aenter__(self):
        """异步上下文管理"""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """确保关闭Session"""
        if self.session:
            await self.session.close()

    @filter.command("vod", "vodd")
    async def unified_search(self, event: AstrMessageEvent, text: str) -> AsyncGenerator[MessageEventResult, None]:
        """统一搜索入口"""
        is_adult = event.command == "vodd"
        api_config = self.api_url_18 if is_adult else self.api_url_vod
        service_type = "成人" if is_adult else "普通"
        
        if not api_config:
            yield event.plain_result(f"⚠️ {service_type}视频服务未启用")
            return
        if not text:
            yield event.plain_result("🔍 请输入搜索内容（示例：/vod 流浪地球）")
            return

        async for msg in self._process_search(event, api_config, text.strip(), len(api_config)):
            yield msg

    async def _process_search(self, event, api_urls, keyword, total_apis):
        """搜索处理流程"""
        try:
            # 并发请求所有API
            tasks = [self._fetch_api_data(url, keyword) for url in api_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 结果聚合
            grouped_data = self._aggregate_results(results)
            if not grouped_data:
                yield event.plain_result(self._build_empty_result(total_apis, 0))
                return
                
            # 消息构建
            success_apis = sum(1 for r in results if not isinstance(r, Exception) and r)
            message = self._construct_message(
                total_apis=total_apis,
                success_apis=success_apis,
                grouped_data=grouped_data
            )
            yield event.plain_result(message)
            
        except Exception as e:
            self.context.logger.error(f"搜索异常: {str(e)}", exc_info=True)
            yield event.plain_result("⚠️ 服务暂时不可用，请稍后重试")

    async def _fetch_api_data(self, api_url, keyword):
        """执行API请求"""
        try:
            encoded_keyword = urllib.parse.quote(keyword)
            async with self.session.get(
                f"{api_url}?ac=videolist&wd={encoded_keyword}",
                allow_redirects=False
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None
        except Exception as e:
            self.context.logger.debug(f"API请求失败 [{api_url}]: {str(e)}")
            return e  # 返回异常用于统计

    def _aggregate_results(self, results):
        """聚合多API结果"""
        grouped = {}
        ordered_titles = []
        
        for html in results:
            if isinstance(html, Exception) or not html:
                continue
                
            for title, url in self._parse_html(html):
                if title not in grouped:
                    grouped[title] = []
                    ordered_titles.append(title)
                grouped[title].append(url)
        
        return {
            "grouped": grouped,
            "ordered_titles": ordered_titles,
            "total": sum(len(urls) for urls in grouped.values())
        }

    def _parse_html(self, html):
        """解析HTML内容"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('rss list video')[:self.records]
            
            for item in items:
                title_elem = item.select_one('name')
                title = title_elem.text.strip() if title_elem else "未知标题"
                
                # 提取所有有效URL
                for dd in item.select('dl > dd'):
                    for url in dd.text.split('#'):
                        if url := url.strip():
                            yield (title, url)
        except Exception as e:
            self.context.logger.warning(f"解析异常: {str(e)}")
            return []

    def _construct_message(self, total_apis, success_apis, grouped_data):
        """构建完整消息"""
        lines = []
        
        # 添加标题
        lines.extend(self._build_header(total_apis, success_apis, grouped_data["total"]))
        
        # 填充内容
        line_count = len(lines)
        for idx, title in enumerate(grouped_data["ordered_titles"], 1):
            title_line = f"{idx}. 【{title}】"
            url_lines = [f"   🎬 {url}" for url in grouped_data["grouped"][title][:3]]  # 每个资源最多显示3条
            
            # 行数控制
            if line_count + len(url_lines) + 1 > MAX_RESULT_LINES:
                lines.append("...（结果已截断）")
                break
                
            lines.append(title_line)
            lines.extend(url_lines)
            line_count += len(url_lines) + 1
        
        # 添加尾部
        lines.extend(self._build_footer())
        return "\n".join(lines)

    def _build_header(self, total_apis, success_apis, total_videos):
        """消息头部模板"""
        return [
            f"🔍 搜索 {total_apis} 个源｜成功 {success_apis} 个",
            f"📊 找到 {total_videos} 条资源",
            "━" * 26
        ]

    def _build_footer(self):
        """消息尾部模板"""
        return [
            "━" * 26,
            "💡 播放提示：",
            "• 移动端：直接复制链接到浏览器",
            "• 电脑端：推荐使用PotPlayer/VLC",
            "━" * 26
        ]

    def _build_empty_result(self, total_apis, success_apis):
        """无结果消息"""
        return (
            f"🔍 搜索 {total_apis} 个源｜成功 {success_apis} 个\n"
            f"{'━'*26}\n"
            "⚠️ 未找到相关资源\n"
            f"{'━'*26}"
        )

from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # 分割API地址并过滤无效项
        self.api_url_vod = [url.strip() for url in config.get("api_url_vod", "").split(',') if url.strip()]
        self.api_url_18 = [url.strip() for url in config.get("api_url_18", "").split(',') if url.strip()]

    async def _common_handler(self, event, api_urls, keyword):
        """支持多API的增强型处理器"""
        if not api_urls:
            yield event.plain_result("⚠️ 服务未正确配置，请联系管理员")
            return

        error_log = []
        for base_url in api_urls:
            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{base_url}?ac=videolist&wd={encoded_keyword}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        if response.status != 200:
                            error_log.append(f"{base_url} 状态码 {response.status}")
                            continue

                        html_content = await response.text()
                        parsed_result, total_count = self._parse_html(html_content)
                        
                        if not parsed_result:
                            error_log.append(f"{base_url} 无结果")
                            continue

                        # 构建统计信息
                        display_count = min(8, total_count)
                        stats_info = (
                            f"🔍 找到 {total_count} 条相关结果 | "
                            f"展示前 {display_count} 条\n"
                            "━" * 30
                        )

                        # 组装完整消息
                        result_msg = [
                            stats_info,
                            parsed_result,
                            "\n" + "*" * 30,
                            "💡 播放提示：",
                            "• 手机：链接粘贴到浏览器地址栏",
                            "• 电脑：使用专业播放器打开",
                            "*" * 30
                        ]
                        yield event.plain_result("\n".join(result_msg))
                        return

            except aiohttp.ClientTimeout:
                error_log.append(f"{base_url} 请求超时")
            except Exception as e:
                error_log.append(f"{base_url} 异常: {str(e)}")

        # 全失败处理
        self.context.logger.error(f"API全失败 | {' | '.join(error_log)}")
        yield event.plain_result("❌ 所有服务暂时不可用，请稍后重试")

    def _parse_html(self, html_content):
        """增强版HTML解析"""
        soup = BeautifulSoup(html_content, 'html.parser')
        all_items = soup.select('rss list video')
        
        processed = []
        max_display = 8  # 最大显示数量
        actual_display = min(len(all_items), max_display)
        
        for idx, item in enumerate(all_items[:max_display], 1):
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            
            # 提取有效链接
            valid_links = []
            for dd in item.select('dl > dd'):
                for url in dd.text.split('#'):
                    clean_url = url.strip()
                    if clean_url:
                        valid_links.append(clean_url)
            
            if valid_links:
                links = "\n   ".join(valid_links)
                processed.append(f"{idx}. 【{title}】\n   🎬 {links}")

        # 返回处理结果和总数
        result_str = "\n".join(processed) if processed else None
        return result_str, len(all_items)

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通视频搜索"""
        if not self.api_url_vod:
            yield event.plain_result("🔧 普通视频服务未配置")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """成人内容搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

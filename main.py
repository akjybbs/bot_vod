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
        attempted = 0
        succeeded = 0
        result_data = None
        total_items = 0

        for base_url in api_urls:
            attempted += 1
            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{base_url}?ac=videolist&wd={encoded_keyword}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        # 记录请求尝试
                        if response.status != 200:
                            error_log.append(f"{base_url} 状态码 {response.status}")
                            continue

                        # 处理有效响应
                        html_content = await response.text()
                        parsed_result, total_count = self._parse_html(html_content)
                        
                        if not parsed_result:
                            error_log.append(f"{base_url} 无有效结果")
                            continue

                        # 成功获取数据
                        succeeded = 1
                        result_data = parsed_result
                        total_items = total_count
                        break  # 成功即终止循环

            except aiohttp.ClientTimeout:
                error_log.append(f"{base_url} 请求超时")
            except Exception as e:
                error_log.append(f"{base_url} 异常: {str(e)}")

            # 已有成功结果则提前退出
            if succeeded:
                break

        # 构建最终响应
        if succeeded:
            display_count = min(8, total_items)
            stats_header = [
                f"🔍 尝试 {attempted} 个源｜成功 {succeeded} 个",
                f"📊 找到 {total_items} 条结果｜展示前 {display_count} 条",
                "━" * 30
            ]
            result_msg = [
                *stats_header,
                result_data,
                "\n" + "*" * 30,
                "💡 播放指南：",
                "• 移动端：直接粘贴链接到浏览器",
                "• 桌面端：推荐使用PotPlayer/VLC播放",
                "*" * 30
            ]
            yield event.plain_result("\n".join(result_msg))
        else:
            error_header = [
                f"❌ 尝试 {attempted} 个源｜成功 {succeeded} 个",
                "⚠️ 所有服务暂时不可用，可能原因："
            ]
            error_body = [
                "1. 所有API服务器繁忙",
                "2. 网络连接异常",
                "3. 内容暂时下架",
                "请稍后重试或联系管理员"
            ]
            self.context.logger.error(f"全API失败 | 请求记录：{' | '.join(error_log)}")
            yield event.plain_result("\n".join([*error_header, *error_body]))
    def _parse_html(self, html_content):
        """新版HTML解析方法，按标题分组剧集"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')
    
        MAX_TITLES = 8  # 最大显示标题数
        processed = []
        title_counter = 0
    
        for item in video_items:
            if title_counter >= MAX_TITLES:
                break
            
            # 提取主标题
            main_title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
        
            # 提取剧集信息
            episodes = []
            for dd in item.select('dl > dd'):
                parts = dd.text.strip().split('$')
                if len(parts) >= 2:
                    ep_name = parts[0].strip()
                    ep_url = parts[1].strip()
                    episodes.append(f"   🎬 {ep_name}${ep_url}")
                elif dd.text.strip():  # 处理没有分隔符的情况
                    ep_url = dd.text.strip()
                    ep_name = f"第{len(episodes)+1:02d}集"
                    episodes.append(f"   🎬 {ep_name}${ep_url}")
        
            if episodes:
                title_counter += 1
                # 组装条目
                entry = [
                    f"{title_counter}. 【{main_title}】",
                    *episodes[:5]  # 每个标题最多显示5个剧集
                ]
                processed.append("\n".join(entry))
    
        total_items = len(video_items)
        return "\n\n".join(processed) if processed else None, total_items

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视搜索"""
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

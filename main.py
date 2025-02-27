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
        # 初始化API列表并过滤空值
        self.api_url_vod = [url.strip() for url in config.get("api_url_vod", "").split(',') if url.strip()]
        self.api_url_18 = [url.strip() for url in config.get("api_url_18", "").split(',') if url.strip()]

    async def _common_handler(self, event, api_urls, keyword):
        """支持多API源聚合的核心处理器"""
        if not api_urls:
            yield event.plain_result("⚠️ 服务未正确配置，请联系管理员")
            return

        error_log = []
        attempted = 0
        succeeded = 0
        collected_results = []  # 收集所有结果
        MAX_DISPLAY = 8         # 最大显示数量

        # 遍历所有API源
        for base_url in api_urls:
            if len(collected_results) >= MAX_DISPLAY:
                break  # 结果数量达标提前终止
            
            attempted += 1
            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{base_url}?ac=videolist&wd={encoded_keyword}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        # 处理HTTP错误
                        if response.status != 200:
                            error_log.append(f"{base_url} 状态码 {response.status}")
                            continue

                        # 解析结果
                        html_content = await response.text()
                        parsed_result, total = self._parse_html(html_content)
                        
                        if not parsed_result:
                            error_log.append(f"{base_url} 无有效结果")
                            continue
                            
                        succeeded += 1
                        # 去重并收集结果
                        for entry in parsed_result.split('\n'):
                            if entry and entry not in collected_results:
                                collected_results.append(entry)
                                if len(collected_results) >= MAX_DISPLAY:
                                    break  # 达到最大数量

            except aiohttp.ClientTimeout:
                error_log.append(f"{base_url} 请求超时")
            except Exception as e:
                error_log.append(f"{base_url} 异常: {str(e)}")

        # 构建最终结果
        if len(collected_results) > 0:
            displayed = collected_results[:MAX_DISPLAY]
            stats_msg = [
                f"🔍 尝试 {attempted} 个源｜成功 {succeeded} 个",
                f"📊 找到 {len(collected_results)} 条结果｜展示前 {len(displayed)} 条",
                "━" * 30
            ]
            result_msg = [
                *stats_msg,
                "\n".join(displayed),
                "\n" + "*" * 30,
                "💡 播放提示：",
                "• 手机：链接粘贴到浏览器地址栏",
                "• 电脑：使用专业播放器打开链接",
                "*" * 30
            ]
            yield event.plain_result("\n".join(result_msg))
        else:
            error_msg = [
                f"❌ 尝试 {attempted} 个源｜成功 {succeeded} 个",
                "⚠️ 所有服务暂时不可用，可能原因：",
                "1. 所有API服务器繁忙",
                "2. 网络连接异常",
                "3. 内容暂时下架",
                "请稍后重试或联系管理员"
            ]
            self.context.logger.error(f"全API失败 | 错误记录：{' | '.join(error_log)}")
            yield event.plain_result("\n".join(error_msg))

    def _parse_html(self, html_content):
        """精准解析HTML结构，确保独立条目显示"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')
        
        processed = []
        MAX_RESULTS = 20  # 提高解析上限
        
        for idx, item in enumerate(video_items[:MAX_RESULTS], 1):
            # 提取主标题（智能去除集数信息）
            raw_title = item.select_one('name').text.strip() if item.select_one('name') else "无标题"
            main_title = raw_title.split('第')[0].split()[0].strip()
            
            # 提取剧集名称（优先从标题获取）
            ep_name = "第{:02d}集".format(idx)
            if '第' in raw_title and '集' in raw_title:
                ep_part = raw_title.split('第')[1].split('集')[0].strip()
                ep_name = f"第{ep_part}集"
            
            # 提取有效链接
            ep_url = ""
            for dd in item.select('dl > dd'):
                parts = dd.text.strip().split('$')
                if len(parts) >= 2:
                    ep_url = parts[-1].strip()  # 始终取最后部分作为链接
                    break
                elif dd.text.strip():
                    ep_url = dd.text.strip()
                    break
            
            if ep_url.startswith('http'):
                processed.append(f"{idx}. 【{main_title}】🎬 {ep_name}${ep_url}")
        
        return "\n".join(processed), len(video_items)

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视资源搜索"""
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

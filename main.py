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
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))

    async def _common_handler(self, event, api_urls, keyword):
        """核心逻辑：按影视名称去重"""
        total_attempts = len(api_urls)
        successful_apis = 0
        seen_titles = set()  # 名称去重集合
        final_results = []   # 最终结果（名称唯一）
        raw_count = 0        # 原始找到总数

        for api_url in api_urls:
            api_url = api_url.strip()
            if not api_url:
                continue

            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        if response.status != 200:
                            continue

                        html_content = await response.text()
                        items = self._parse_html(html_content)
                        raw_count += len(items)  # 累加原始数据量

                        if items:
                            successful_apis += 1
                            # 名称去重处理
                            for title, url in items:
                                if title not in seen_titles:
                                    seen_titles.add(title)
                                    final_results.append((title, url))

            except Exception as e:
                self.context.logger.error(f"视频查询异常: {str(e)}")
                continue

        # 处理显示结果
        display_results = final_results[:self.records]  # 限制显示条数
        unique_count = len(final_results)

        if display_results:
            result_lines = [f"{idx}. 【{title}】\n   🎬 {url}" 
                           for idx, (title, url) in enumerate(display_results, 1)]
            
            msg = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                f"📊 原始结果 {raw_count} 条｜去重后 {unique_count} 条｜显示前{len(display_results)}条",
                "━" * 30,
                "📺 查询结果：",
                *result_lines,
                "\n" + "━" * 30,
                "💡 同名资源已自动去重，优先显示最早找到的版本",
                "━" * 30
            ]
            yield event.plain_result("\n".join(msg))
        else:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━' * 30}\n⚠️ 未找到相关资源")

    def _parse_html(self, html_content):
        """解析HTML（保持原始顺序）"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')
        
        results = []
        for item in video_items[:self.records]:  # 控制单API处理量
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            # 取第一个有效的播放链接
            first_url = next((url.strip() for dd in item.select('dl > dd') 
                            for url in dd.text.split('#') if url.strip()), None)
            if first_url:
                results.append((title, first_url))
        return results

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视搜索"""
        if not any(self.api_url_vod):
            yield event.plain_result("🔧 普通视频服务未配置")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """🔞成人内容搜索"""
        if not any(self.api_url_18):
            yield event.plain_result("🔞 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

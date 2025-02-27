from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "多源视频搜索（使用 /vod 或 /vodd + 电影名）", "1.2")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # 解析多URL配置
        self.api_url_vod = self._parse_urls(config.get("api_url_vod", ""))
        self.api_url_18 = self._parse_urls(config.get("api_url_18", ""))
    
    def _parse_urls(self, config_str: str) -> list:
        """将逗号分隔的字符串转换为URL列表"""
        return [url.strip() for url in config_str.split(",") if url.strip()]

    async def _common_handler(self, event, api_urls: list, keyword: str):
        """支持多API源的核心逻辑"""
        # 空配置检查
        if not api_urls:
            yield event.plain_result("⚠️ 该服务未配置可用API源")
            return

        all_results = []
        error_count = 0
        
        # 遍历所有API源
        for api_url in api_urls:
            try:
                encoded_keyword = urllib.parse.quote(keyword)
                query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=10) as response:
                        # 跳过无效响应
                        if response.status != 200:
                            continue
                            
                        # 解析结果
                        html_content = await response.text()
                        if parsed := self._parse_html(html_content):
                            all_results.append(f"【{api_url}】\n{parsed}")
                            
            except Exception as e:
                error_count += 1
                self.context.logger.warning(f"API源 {api_url} 请求失败: {str(e)}")

        # 结果处理
        if not all_results:
            yield event.plain_result("🔍 所有API源均未找到结果" if error_count == 0 
                                   else "⚠️ 搜索失败，请稍后重试")
            return
            
        # 构建最终消息
        result_msg = [
            f"📺 共查询到 {len(all_results)} 个有效结果:",
            "\n\n".join(all_results),
            "\n" + "*" * 30,
            "💡 搜索统计:",
            f"- 成功源: {len(all_results)} 个",
            f"- 失败源: {error_count} 个",
            "*" * 30
        ]
        yield event.plain_result("\n".join(result_msg))

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通资源多源搜索"""
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """成人资源多源搜索"""
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg

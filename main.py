from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import time
from typing import Dict

# 全局状态存储
TEST_STATES: Dict[int, Dict] = {}

@register("timeout_test", "tester", "20秒交互测试插件", "1.0")
class TimeoutTestPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.context = context
        
    @filter.command("testpage")
    async def start_test(self, event: AstrMessageEvent):
        """启动分页测试"""
        user_id = event.get_sender_id()
        
        # 生成测试分页数据
        pages = [
            "📄 第1页/3（测试内容：A）",
            "📄 第2页/3（测试内容：B）",
            "📄 第3页/3（测试内容：C）"
        ]
        
        TEST_STATES[user_id] = {
            "pages": pages,
            "timestamp": time.time(),
            "current_page": 0
        }
        
        yield event.chain_result([
            Plain("⏱ 20秒分页测试开始！"),
            Plain("当前页码：1/3"),
            Plain("请回复数字跳转页面")
        ])

    @filter.message_handle
    async def handle_input(self, event: AstrMessageEvent):
        """处理所有消息"""
        user_id = event.get_sender_id()
        current_time = time.time()
        
        # 清理过期状态
        expired_users = [uid for uid, s in TEST_STATES.items() 
                       if current_time - s["timestamp"] > 20]
        for uid in expired_users:
            del TEST_STATES[uid]
            self.context.logger.info(f"已清理过期用户 {uid}")
        
        # 检查有效状态
        if user_id not in TEST_STATES:
            return
        
        state = TEST_STATES[user_id]
        message = event.message_str.strip()
        
        # 处理数字输入
        if message.isdigit():
            page_num = int(message)
            total_pages = len(state["pages"])
            
            if 1 <= page_num <= total_pages:
                state["current_page"] = page_num - 1
                state["timestamp"] = current_time
                
                yield event.chain_result([
                    Plain(f"🔄 跳转到第 {page_num} 页"),
                    Plain(state["pages"][page_num-1]),
                    Plain(f"剩余时间：{20 - int(current_time - state['timestamp'])}秒")
                ])
            else:
                yield event.plain_result(f"⚠️ 请输入1-{total_pages}之间的数字")
        
        # 处理非数字输入
        else:
            yield event.plain_result("⛔ 输入无效，请输入数字")

    @filter.command("teststatus")
    async def check_status(self, event: AstrMessageEvent):
        """检查当前状态"""
        user_id = event.get_sender_id()
        if user_id in TEST_STATES:
            state = TEST_STATES[user_id]
            remain_time = 20 - (time.time() - state["timestamp"])
            yield event.plain_result(
                f"🕒 剩余时间：{max(0, int(remain_time))}秒\n"
                f"📖 当前页码：{state['current_page'] + 1}/{len(state['pages'])}"
            )
        else:
            yield event.plain_result("❌ 没有活跃的测试会话")

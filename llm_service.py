"""
DeepSeek API封装服务
提供LLM调用的统一接口，支持降级处理
"""
import os
import json
import threading
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# 全局超时时间（秒）- 缩短超时，加快响应
LLM_TIMEOUT = 15

# 预设模板（API调用失败时降级使用）
BLESSING_TEMPLATES = {
    "闺蜜": "生日快乐呀宝！🎉 新的一岁继续一起疯一起闹~",
    "搭子": "生快！🎂 期待更多精彩瞬间，先收下这份祝福！",
    "同学": "生日快乐！愿学业顺利，天天开心！🎈",
    "家人": "生日快乐！🥳 身体健康，万事如意！",
    "好友": "生日快乐！🎁 友谊长存！",
    "同事": "生日快乐！🎂 职场顺利~",
    "画友": "生日快乐！🎨 创作顺利~",
    "default": "生日快乐！🎉 天天开心~"
}

GREETING_TEMPLATES = {
    "考研结束": "听说考研出分了！最近怎么样？",
    "降温搭子": "最近忙啥呢？好久没一起了~",
    "沉寂好友": "突然想起你啦！最近怎么样？",
    "default": "嗨！好久不见~"
}


class LLMService:
    def __init__(self):
        api_key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY') or ''
        
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = "deepseek-v4-pro"
    
    def _call_llm(self, messages, temperature=0.7, timeout=None):
        """调用DeepSeek API，带超时处理"""
        if timeout is None:
            timeout = LLM_TIMEOUT
        
        result = [None]
        error = [None]
        
        def _call():
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    stream=False
                )
                result[0] = response.choices[0].message.content
            except Exception as e:
                error[0] = e
        
        thread = threading.Thread(target=_call)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            print(f"[LLM] 调用超时（{timeout}秒）")
            return None
        
        if error[0]:
            print(f"[LLM] 调用失败: {error[0]}")
            return None
        
        return result[0]
    
    def extract_group_info(self, messages_text: str, group_name: str = "") -> dict:
        """
        从群消息中提取关键信息（DDL、投票、@提醒等）
        返回结构化JSON，格式简单明确
        """
        prompt = f"""【任务】从群聊消息中提取需要关注的事项。

群名称：{group_name}
消息内容：
{messages_text}

【输出格式】只返回JSON，不要其他内容：
{{"items": [
  {{"type": "ddl", "content": "具体任务内容", "deadline": "截止时间", "urgency": "high/medium/low", "action": "需要的行动"}},
  {{"type": "vote", "content": "投票内容", "options": ["选项1", "选项2"], "urgency": "medium"}},
  {{"type": "at_reminder", "content": "@你的内容", "sender": "发送者", "urgency": "high"}},
  {{"type": "announcement", "content": "公告内容", "urgency": "medium"}}
]}}

【规则】
1. 只提取重要事项，忽略普通聊天
2. ddl类型：截止日期相关的任务
3. vote类型：需要投票的选择
4. at_reminder类型：有人@你或提到重要提醒
5. announcement类型：官方公告通知
6. 如果没有重要事项，返回空数组: {{"items": []}}
7. urgency: 高(high)=今天内要处理，中(medium)=近期要处理，低(low)=有空再看"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.3, timeout=20)
        
        if result:
            try:
                # 提取JSON（处理可能的markdown代码块）
                text = result.strip()
                if text.startswith("```"):
                    # 去掉markdown代码块
                    lines = text.split('\n')
                    text = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])
                
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "items" in parsed:
                    return parsed
                elif isinstance(parsed, list):
                    return {"items": parsed}
                else:
                    return {"items": [parsed]}
            except json.JSONDecodeError as e:
                print(f"[LLM] JSON解析失败: {e}, 原始结果: {result[:200]}")
        
        # 快速降级：关键词匹配
        return self._fallback_extract(messages_text)
    
    def _fallback_extract(self, text: str) -> dict:
        """降级处理：使用规则快速提取"""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in ['ddl', '截止', 'deadline', '前提交', '明天', '今天', '今晚']):
                results.append({
                    "type": "ddl",
                    "content": line.strip()[:100],
                    "urgency": "high",
                    "action": "按时完成"
                })
            elif any(kw in line_lower for kw in ['投票', 'vote', '扣1', '扣2', '选项']):
                results.append({
                    "type": "vote",
                    "content": line.strip()[:80],
                    "urgency": "medium",
                    "action": "请投票"
                })
            elif '@' in line and any(kw in line_lower for kw in ['重要', '提醒', '通知']):
                results.append({
                    "type": "at_reminder",
                    "content": line.strip()[:80],
                    "urgency": "high",
                    "action": "查看并回复"
                })
        
        return {"items": results[:5]}  # 最多返回5条
    
    def generate_blessing(self, contact_name: str, relationship: str, 
                         chat_history: str, birthday_type: str = "birthday",
                         user_tone: str = "") -> str:
        """生成个性化祝福文案"""
        prompt = f"""为好友 {contact_name} 写一条生日祝福。

关系：{relationship}
聊天历史：{chat_history}

要求：50字以内，自然亲切，像朋友聊天，可以适当用emoji。

直接返回祝福语，不要其他内容。"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], timeout=12)
        
        if result:
            return result.strip()
        
        return f"生日快乐呀{contact_name}！🎂 愿你天天开心~"
    
    def generate_greeting(self, contact_name: str, relationship: str,
                         topic_context: str, event_signal: str = "") -> str:
        """生成重新激活沉寂关系的开口建议"""
        prompt = f"""为重新联系好友 {contact_name} 写一条开场白。

关系：{relationship}
话题背景：{topic_context}
触发事件：{event_signal}

要求：30字以内，自然随意，像老朋友聊天。

直接返回开场白，不要其他内容。"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], timeout=10)
        
        if result:
            return result.strip()
        
        return f"嘿~好久不见，最近怎么样？"

    def generate_reply(self, contact_name: str, relationship: str, 
                       message: str, chat_history: list = None) -> str:
        """生成上下文感知的回复"""
        prompt = f"""你是一个QQ用户，正在和朋友聊天。

对方：{contact_name}
关系：{relationship}
发来的消息："{message}"

要求：1-2句话，自然口语化，像QQ聊天。

直接返回回复，不要其他内容。"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.8, timeout=8)
        
        if result:
            return result.strip()
        
        # 快速模板回复
        if '?' in message or '？' in message:
            return "让我想想~"
        return "好的！"


# 全局单例
llm_service = LLMService()

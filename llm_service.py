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

# 全局超时时间（秒）
LLM_TIMEOUT = 20

# 预设模板（API调用失败时降级使用）
BLESSING_TEMPLATES = {
    "闺蜜": "生日快乐呀宝！🎉 新的一岁继续一起疯一起闹，愿所有美好都如期而至～",
    "搭子": "生快！🎂 感谢搭子时光，期待更多精彩瞬间，先收下这份祝福！",
    "同学": "生日快乐！愿学业顺利，天天开心！🎈",
    "家人": "生日快乐！🥳 身体健康，万事如意！",
    "好友": "生日快乐！🎁 友谊长存！",
    "同事": "生日快乐！🎂 职场顺利，一起加油～",
    "画友": "生日快乐！🎨 创作顺利，多出好作品～",
    "default": "生日快乐！🎉 愿你天天开心，万事顺意！"
}

GREETING_TEMPLATES = {
    "考研结束": "听说考研出分了！不管结果怎样，这一年的努力都值得骄傲，最近怎么样？",
    "降温搭子": "最近忙啥呢？好久没一起浪了，周末有空吗？",
    "沉寂好友": "突然想起你啦！最近怎么样？",
    "工作搭子降温": "最近加班多吗？咖啡探店好久没去了~",
    "插画友降温": "最近有什么新作品吗？好久没交流了~",
    "default": "嗨！好久不见，最近怎么样？"
}

class LLMService:
    def __init__(self):
        # 移除 http_proxy/https_proxy 环境变量避免冲突
        env = os.environ.copy()
        env.pop('http_proxy', None)
        env.pop('https_proxy', None)
        env.pop('HTTP_PROXY', None)
        env.pop('HTTPS_PROXY', None)
        
        self.client = OpenAI(
            api_key=os.environ.get('DEEPSEEK_API_KEY'),
            base_url="https://api.deepseek.com",
            http_client=None  # 避免代理问题
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
            # 超时
            print(f"LLM API调用超时（{timeout}秒）")
            return None
        
        if error[0]:
            print(f"LLM API调用失败: {error[0]}")
            return None
        
        return result[0]
    
    def extract_group_info(self, messages_text: str) -> dict:
        """
        从群消息中提取关键信息（DDL、投票、@提醒等）
        返回结构化JSON
        """
        prompt = f"""从以下群聊消息中提取关键信息，识别DDL、投票、@提醒等重要内容。

消息内容：
{messages_text}

请以JSON格式返回，字段说明：
- type: 类型 (deadline/vote/at_reminder/announcement/normal)
- content: 内容摘要
- deadline: 截止时间（如果有）
- urgency: 紧急程度 (high/medium/low)
- source_group: 来源群名
- action_required: 需要采取的行动

只返回关键信息项，不要返回普通聊天内容。如果有多条关键信息，以数组形式返回。"""

        result = self._call_llm([
            {"role": "system", "content": "你是一个信息提取助手，擅长从聊天记录中提取关键任务和提醒。"},
            {"role": "user", "content": prompt}
        ])
        
        if result:
            try:
                # 尝试解析JSON
                return json.loads(result)
            except:
                # 如果不是有效JSON，返回提示
                return {"error": "提取失败", "raw": result}
        
        # 降级处理：使用关键词匹配
        return self._fallback_extract(messages_text)
    
    def _fallback_extract(self, text: str) -> dict:
        """降级处理：使用规则提取"""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in ['ddl', '截止', 'deadline', '截止时间', '前提交']):
                results.append({
                    "type": "deadline",
                    "content": line.strip(),
                    "urgency": "medium",
                    "action_required": "按时完成并提交"
                })
            elif any(kw in line_lower for kw in ['投票', 'vote', '选项', '扣1', '扣2']):
                results.append({
                    "type": "vote",
                    "content": line.strip(),
                    "urgency": "medium",
                    "action_required": "请投票"
                })
            elif '@' in line and any(kw in line_lower for kw in ['重要', '提醒', '通知']):
                results.append({
                    "type": "at_reminder",
                    "content": line.strip(),
                    "urgency": "high",
                    "action_required": "查看并回复"
                })
        
        return {"items": results} if results else {"items": []}
    
    def generate_blessing(self, contact_name: str, relationship: str, 
                         chat_history: str, birthday_type: str = "birthday",
                         user_tone: str = "") -> str:
        """
        生成个性化祝福文案
        
        Args:
            contact_name: 收祝福的人名
            relationship: 关系类型
            chat_history: 聊天历史摘要
            birthday_type: 祝福类型（birthday/节日）
            user_tone: 用户说话风格描述
        """
        msg_type = "生日" if birthday_type == "birthday" else "节日"
        
        # 构建用户语气描述
        tone_instruction = ""
        if user_tone:
            tone_instruction = f"\n\n用户说话风格：{user_tone}\n请模仿用户的说话风格和语气生成祝福。"
        
        prompt = f"""为好友 {contact_name} 生成一条{msg_type}祝福。

关系类型：{relationship}
聊天历史摘要：{chat_history}{tone_instruction}

要求：
1. 语言自然亲切，符合日常聊天风格
2. 模仿用户的说话风格和语气
3. 融入聊天历史中的共同话题或回忆
4. 长度适中（50字以内）
5. 可以适当使用emoji，但不要太多

直接返回祝福文案，不要其他内容。"""

        # 使用3秒超时
        result = self._call_llm([
            {"role": "system", "content": "你是一个温暖的祝福语生成助手。"},
            {"role": "user", "content": prompt}
        ], timeout=20)
        
        # 失败则重试一次
        if not result:
            result = self._call_llm([
                {"role": "system", "content": "你是一个温暖的祝福语生成助手。"},
                {"role": "user", "content": prompt}
            ], timeout=20)
        
        if result:
            return result.strip()
        
        # 重试两次都失败，返回通用祝福
        return f"生日快乐呀{contact_name}！🎂 愿你天天开心，万事如意~"
    
    def generate_greeting(self, contact_name: str, relationship: str,
                         topic_context: str, event_signal: str = "") -> str:
        """
        生成重新激活沉寂关系的开口建议
        """
        prompt = f"""为重新联系好友 {contact_name} 生成一条自然的开场白。

关系类型：{relationship}
已有话题背景：{topic_context}
事件触发信号：{event_signal}

要求：
1. 自然不刻意，像是老朋友之间的随意聊天
2. 可以提及对方的近况或共同话题
3. 不要太正式或太刻意
4. 长度适中（30字以内）
5. 符合日常社交习惯

直接返回开场白，不要其他内容。"""

        result = self._call_llm([
            {"role": "system", "content": "你是一个社交助手，擅长帮助用户自然地重新建立联系。"},
            {"role": "user", "content": prompt}
        ])
        
        # 失败则重试一次
        if not result:
            result = self._call_llm([
                {"role": "system", "content": "你是一个社交助手，擅长帮助用户自然地重新建立联系。"},
                {"role": "user", "content": prompt}
            ])
        
        if result:
            return result.strip()
        
        # 重试两次都失败，返回通用问候
        return f"嘿~好久不见，最近怎么样？"
    
    def extract_topics(self, text: str, max_topics: int = 5) -> list:
        """
        从文本中抽取话题标签
        """
        prompt = f"""从以下文本中抽取关键话题标签，最多{max_topics}个。

文本内容：
{text}

返回格式：JSON数组，如 ["游戏-王者荣耀", "考研", "音乐"]

只返回标签数组，不要其他内容。"""

        result = self._call_llm([
            {"role": "system", "content": "你是一个话题标签提取助手。"},
            {"role": "user", "content": prompt}
        ])
        
        if result:
            try:
                return json.loads(result)
            except:
                return []
        return []
    
    def generate_reply(self, contact_name: str, relationship: str, 
                       message: str, chat_history: list = None) -> str:
        """
        生成上下文感知的回复
        回复要短（1-2句话），像QQ聊天一样自然
        """
        # 构建上下文
        history_section = ""
        if chat_history and len(chat_history) > 0:
            history_text = "\n".join([
                f"{h.get('sender', '对方')}: {h.get('content', '')}" 
                for h in chat_history[-8:]  # 取最近8条
            ])
            history_section = f"\n\n【最近聊天记录】\n{history_text}\n\n请根据聊天记录的上下文来回复，确保你的回复和对话内容连贯。"
        
        prompt = f"""你是一个QQ用户，名叫{contact_name}。

【关系】{relationship}
【对方发来的消息】"{message}"
{history_section}
请生成一条自然的回复。
要求：
1. 回复要短，1-2句话
2. 像QQ聊天一样自然、口语化
3. 可以用一些网络用语和emoji
4. 不要太正式
5. 根据关系类型调整语气：
   - 搭子/好友/画友：随意、幽默，如"哈哈" "ok" "走起"
   - 室友/同事：亲近随意，如"好嘞" "来" "冲"
   - 同学：礼貌但有距离，如"好的" "收到" "嗯嗯"
   - 家人：温暖关心，如"知道了" "放心吧"
6. 必须结合聊天记录的上下文来回复，不要答非所问

直接返回回复内容，不要其他内容。"""

        result = self._call_llm([
            {"role": "system", "content": f"你是一个QQ用户，名叫{contact_name}，正在和朋友聊天。你说话自然、随意，像真实的年轻人。"},
            {"role": "user", "content": prompt}
        ], temperature=0.8, timeout=8)
        
        if result:
            return result.strip()
        
        # 超时或失败时的模板回复
        return self._fallback_reply(message, relationship)
    
    def _fallback_reply(self, message: str, relationship: str) -> str:
        """上下文模板回复（作为LLM失败的fallback）"""
        message_lower = message.lower()
        
        # 根据消息内容匹配回复
        if any(kw in message_lower for kw in ['生日', '祝福', '快乐']):
            replies = {
                '搭子': ['哈哈谢谢！感动了😭', '太棒了！今晚一起开黑！'],
                '好友': ['哈哈谢谢！开心！', '收到！友谊万岁！'],
                '同学': ['谢谢祝福！😊', '哈哈谢谢！'],
                '室友': ['哈哈谢谢！今晚请我吃饭！', '收到！兄弟够意思！'],
                '家人': ['谢谢宝贝！爱你❤️', '收到！妈妈也爱你~'],
                'default': ['哈哈谢谢！', '太感动了！']
            }
        elif any(kw in message_lower for kw in ['练琴', '练吉他', '吉他', '练', '学']):
            replies = {
                '搭子': ['好！一起练！', '走起！', 'ok！'],
                '好友': ['好的~', '走起！'],
                'default': ['好的！', 'ok！']
            }
        elif any(kw in message_lower for kw in ['帮忙', '帮', '借']):
            replies = {
                '搭子': ['好呀没问题~', '交给我！'],
                '好友': ['收到！', '好的~'],
                '室友': ['好嘞！', '来！'],
                '同学': ['好的，明白了', '没问题'],
                '家人': ['知道了，放心吧', '放心吧妈'],
                'default': ['好呀！', '没问题~']
            }
        elif any(kw in message_lower for kw in ['在哪', '什么时候', '几点', '几点见', '去哪']):
            replies = {
                '搭子': ['在老地方！', '下午三点？'],
                '好友': ['老地方见~', '晚上？'],
                '室友': ['老地方！', '走！'],
                '同学': ['到时候群里说', '看群通知吧'],
                'default': ['晚点再说？', '我看看~']
            }
        elif any(kw in message_lower for kw in ['来', '走', '冲', '走起', '约']):
            replies = {
                '搭子': ['来！', '走起！', '冲！'],
                '好友': ['走！', 'ok！'],
                '室友': ['来！马上！', '冲冲冲！'],
                'default': ['好！', 'ok！']
            }
        elif '?' in message or '？' in message:
            replies = {
                '搭子': ['让我想想...', '嗯...有道理！'],
                '好友': ['让我想想', '好问题！'],
                '同学': ['我也不太确定', '应该是吧'],
                'default': ['嗯...', '对呀！', '有道理']
            }
        else:
            replies = {
                '搭子': ['哈哈', 'ok', '走起！', 'xswl', '收到！'],
                '好友': ['好的！', '收到~', '嗯嗯'],
                '室友': ['好嘞', '来', '收到！', '冲'],
                '同学': ['好的', '收到', '嗯嗯'],
                '家人': ['知道了', '放心吧', '好~'],
                '同事': ['好的！', '收到~', 'okk'],
                '画友': ['哈哈！', '收到~', '好呀'],
                'default': ['好的！', '收到~', '嗯嗯']
            }
        
        contact_replies = replies.get(relationship, replies['default'])
        return contact_replies[hash(message) % len(contact_replies)]

# 全局单例

    def analyze_social_data(self, profile, scan_results, user_tone=""):
        """基于扫描结果，用LLM生成个性化分析和建议"""
        prompt = f"""你是QBuddy，一个QQ智能助手。请基于以下用户的社交数据分析结果，生成个性化的提醒和建议。

用户画像：{json.dumps(profile.get('persona', {}), ensure_ascii=False)}
扫描结果：{json.dumps(scan_results, ensure_ascii=False)}
用户语气：{user_tone}

请按以下格式输出：
1. 每个发现都要给出具体的行动建议
2. 语气要像朋友一样亲切
3. 优先级排序：最紧急的放前面

直接输出分析结果，不要其他内容。"""
        
        result = self._call_llm([
            {"role": "system", "content": "你是QBuddy，一个贴心的QQ智能助手。"},
            {"role": "user", "content": prompt}
        ], timeout=20)
        
        return result or "分析完成，请查看下方卡片详情~"

llm_service = LLMService()
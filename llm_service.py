"""
DeepSeek API封装服务
提供LLM调用的统一接口，用于图谱构建和消息分析
"""
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMService:
    def __init__(self):
        api_key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY') or ''
        
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = "deepseek-v4-pro"
    
    def _call_llm(self, messages, temperature=0.3, max_tokens=4000):
        """
        调用DeepSeek API
        不设置超时限制，让LLM完整分析
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[LLM] 调用失败: {e}")
            return None
    
    def analyze_messages_for_graph(self, messages: list, role_name: str = "我") -> dict:
        """
        分析消息序列，构建或更新图谱
        返回图谱操作指令：add_node / update_node / delete_node
        
        Args:
            messages: 消息列表，每条包含 sender, content, time
            role_name: 当前用户名称，用于识别哪些消息是发给自己的
        
        Returns:
            {
                "nodes_to_add": [...],      # 需要新增的节点
                "nodes_to_update": [...],   # 需要更新的节点
                "nodes_to_delete": [...],   # 需要删除的节点
                "edges_to_add": [...],       # 需要新增的边
                "tags": [...],               # 标签，用于后续推送整合
                "summary": "分析摘要"
            }
        """
        # 格式化消息
        messages_text = self._format_messages(messages)
        
        prompt = f"""【任务】分析以下QQ群聊消息，构建社交关系图谱。

当前用户：{role_name}

消息内容：
{messages_text}

【分析要求】
1. 识别群聊中的关键人物（频繁互动的人、群管理员、发起活动的人）
2. 识别重要事件（DDL、投票、活动、打卡等）
3. 识别人物之间的关系（同班同学、搭子、室友、群友等）
4. 为每个实体打上标签，便于后续推送整合

【输出格式】严格返回JSON：
{{
    "nodes_to_add": [
        {{
            "id": "person_1",           // 节点ID，唯一标识
            "name": "小王",              // 节点名称
            "type": "contact",           // contact(联系人) | event(事件)
            "properties": {{
                "identity": "同学/搭子/群友/老师等",
                "tags": ["考研", "游戏"],  // 标签，用于推送整合
                "personality": "性格描述",
                "interests": ["游戏", "音乐"]
            }},
            "urgency": "high/medium/low",  // 紧急程度
            "action_hint": "需要的行动"      // 如：回复、投票、完成DDL
        }}
    ],
    "edges_to_add": [
        {{
            "source": "user",           // 源节点ID（user表示当前用户）
            "target": "person_1",       // 目标节点ID
            "relationship": "搭子/同学/群友",
            "strength": 0.8,             // 关系强度 0-1
            "interaction_type": "日常聊天/共同活动/搭子互动"
        }}
    ],
    "tags": ["考研相关", "紧急DDL", "投票待处理"],  // 全局标签，用于后续推送整合
    "summary": "本群有3个搭子，1个重要DDL需要处理"
}}

【规则】
1. 只识别重要人物和事件，忽略普通闲聊
2. contact类型节点需要有明确的身份标识
3. event类型节点需要有截止时间或明确的行动项
4. tags用于后续推送整合，确保重要信息不遗漏
5. 如果没有新增内容，返回空数组：{{"nodes_to_add": [], "edges_to_add": [], "tags": [], "summary": "无重要信息"}}
6. 严格返回JSON，不要其他内容"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.3)
        
        if result:
            try:
                # 提取JSON
                text = result.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]
                
                parsed = json.loads(text)
                return self._validate_graph_result(parsed)
            except json.JSONDecodeError as e:
                print(f"[LLM] JSON解析失败: {e}")
                print(f"[LLM] 原始结果: {result[:500]}")
        
        return self._empty_result()
    
    def analyze_new_message(self, message: dict, current_graph: dict = None) -> dict:
        """
        分析单条新消息，判断是否需要更新图谱
        
        Args:
            message: 单条消息，包含 sender, content, time
            current_graph: 当前图谱数据（可选）
        
        Returns:
            {{
                "action": "add_node|update_node|delete_node|none",
                "node": {...},     // 如果action不是none
                "reason": "原因说明"
            }}
        """
        sender = message.get("sender", "")
        content = message.get("content", "")
        time = message.get("time", "")
        
        prompt = f"""【任务】分析一条新消息，判断是否需要在图谱中添加/更新/删除节点。

新消息：
[{time}] {sender}: {content}

当前图谱概况：
{self._format_graph_summary(current_graph)}

【分析要求】
1. 如果消息包含重要信息（DDL、投票、@提醒、活动邀请），可能需要添加event节点
2. 如果消息来自新认识的人，可能需要添加contact节点
3. 如果消息表示取消/结束某事项，需要标记删除
4. 结合当前图谱判断，避免重复添加

【输出格式】严格返回JSON：
{{
    "action": "add_node|update_node|delete_node|none",
    "node": {{
        "id": "可选，指定节点ID",
        "name": "节点名称",
        "type": "contact|event",
        "properties": {{}},
        "urgency": "high/medium/low",
        "action_hint": "需要的行动"
    }},
    "edge": {{
        "target": "关联的节点ID",
        "relationship": "关系类型",
        "strength": 0.5
    }},
    "reason": "判断原因",
    "tags": ["相关标签"]  // 用于后续推送整合
}}

如果没有重要操作，返回：{{"action": "none", "reason": "普通闲聊，无需处理"}}"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.3)
        
        if result:
            try:
                text = result.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]
                
                return json.loads(text)
            except json.JSONDecodeError:
                return {"action": "none", "reason": "解析失败"}
        
        return {"action": "none", "reason": "LLM调用失败"}
    
    def generate_blessing(self, contact_name: str, relationship: str, 
                         chat_history: str, birthday_type: str = "birthday") -> str:
        """生成个性化祝福文案"""
        prompt = f"""为好友 {contact_name} 写一条生日祝福。

关系：{relationship}
聊天历史：{chat_history}

要求：50字以内，自然亲切，像朋友聊天，可以适当用emoji。

直接返回祝福语，不要其他内容。"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.8)
        
        if result:
            return result.strip()
        
        return f"生日快乐呀{contact_name}！🎂"
    
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
        ], temperature=0.8)
        
        if result:
            return result.strip()
        
        return f"嘿~好久不见~"
    
    def generate_reply(self, contact_name: str, relationship: str, 
                       message: str) -> str:
        """生成回复"""
        prompt = f"""你是一个QQ用户，正在和朋友聊天。

对方：{contact_name}
关系：{relationship}
发来的消息："{message}"

要求：1-2句话，自然口语化，像QQ聊天。

直接返回回复，不要其他内容。"""

        result = self._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.8)
        
        if result:
            return result.strip()
        
        return "好的！"
    
    # ============ 辅助方法 ============
    
    def _format_messages(self, messages: list) -> str:
        """格式化消息列表"""
        lines = []
        for msg in messages:
            sender = msg.get("sender", "")
            content = msg.get("content", "")
            time = msg.get("time", "")
            msg_type = msg.get("type", "normal")
            
            # 标记重要消息类型
            type_marker = ""
            if msg_type == "announcement":
                type_marker = "[公告]"
            elif msg_type == "vote":
                type_marker = "[投票]"
            elif msg_type == "at_reminder":
                type_marker = "[@提醒]"
            elif msg_type == "ddl":
                type_marker = "[DDL]"
            
            lines.append(f"[{time}] {sender}: {type_marker}{content}")
        
        return "\n".join(lines)
    
    def _format_graph_summary(self, graph: dict) -> str:
        """格式化图谱摘要"""
        if not graph:
            return "图谱为空"
        
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        
        node_names = [n.get("name", "") for n in nodes[:10]]
        return f"已有{len(nodes)}个节点，{len(edges)}条边。包括：{', '.join(node_names)}"
    
    def _validate_graph_result(self, result: dict) -> dict:
        """验证并补全图谱结果"""
        default_result = self._empty_result()
        
        # 确保所有必要字段存在
        for key in ["nodes_to_add", "edges_to_add", "tags"]:
            if key not in result:
                result[key] = default_result.get(key, [])
        
        for key in ["nodes_to_update", "nodes_to_delete"]:
            if key not in result:
                result[key] = default_result.get(key, [])
        
        result["summary"] = result.get("summary", "")
        
        return result
    
    def _empty_result(self) -> dict:
        """返回空结果"""
        return {
            "nodes_to_add": [],
            "nodes_to_update": [],
            "nodes_to_delete": [],
            "edges_to_add": [],
            "tags": [],
            "summary": "无重要信息"
        }


# 全局单例
llm_service = LLMService()

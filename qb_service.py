"""
QBuddy 核心服务模块
实现完整的产品逻辑：
1. LLM分析消息构建图谱
2. 蒸馏用户语气生成skill.md
3. 检索QQ动态、频道数据
4. 云端消息监听
5. Temperature监控+主动拉起
6. 聚合卡片推送
7. QBuddy对话+Tool Calling
8. 动态阈值调整
"""
import os
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from collections import defaultdict

from llm_service import llm_service
from graph_engine import GraphEngine


# ============ 用户语气 Skill.md 生成 ============

class UserSkillExtractor:
    """步骤2：从用户聊天数据中蒸馏用户语气，生成 skill.md"""
    
    def __init__(self, llm_service):
        self.llm = llm_service
    
    def extract_skill_from_messages(self, user_messages: List[dict], profile: dict = None) -> str:
        """
        从用户的消息历史中提取语气特征，生成 skill.md
        
        Args:
            user_messages: 用户发送的消息列表
            profile: 用户画像（可选）
        
        Returns:
            skill.md 格式的字符串
        """
        # 格式化用户消息
        messages_text = self._format_user_messages(user_messages)
        
        prompt = f"""【任务】分析以下用户的聊天记录，提取用户的说话风格和语气特征。

用户消息：
{messages_text}

用户基本信息：
{json.dumps(profile or {}, ensure_ascii=False, indent=2)}

【输出要求】
请生成一份用户语气风格文档（skill.md），包含：
1. 称呼习惯：用户喜欢怎么称呼朋友（哥/姐/小+姓/直接叫名字等）
2. 语气特征：活泼/稳重/幽默/直接等
3. 常用词汇：高频使用的网络用语、emoji、语气词
4. 标点习惯：感叹号使用频率、问句风格
5. 话题偏好：经常聊什么
6. 回避事项：用户不喜欢什么话题或说话方式

【输出格式】
严格返回JSON：
{{
    "skill_name": "用户语气风格",
    "称呼习惯": "...",
    "语气特征": "...",
    "常用词汇": ["...", "..."],
    "emoji使用": "...",
    "标点习惯": "...",
    "话题偏好": ["...", "..."],
    "回避事项": ["...", "..."],
    "示例句子": ["...", "..."],
    "tldr": "一句话描述用户风格"
}}

如果没有足够的聊天记录，返回：
{{"skill_name": "默认风格", "tldr": "普通聊天风格"}}"""

        result = self.llm._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.5)
        
        if result:
            try:
                text = result.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]
                
                skill_data = json.loads(text)
                
                # 转换为 markdown 格式
                return self._to_markdown(skill_data)
            except:
                return self._default_skill_md()
        
        return self._default_skill_md()
    
    def _format_user_messages(self, messages: List[dict]) -> str:
        """格式化用户消息"""
        lines = []
        for msg in messages[:100]:  # 最多取100条
            content = msg.get("content", "")
            time_str = msg.get("time", "")
            if content:
                lines.append(f"[{time_str}] {content}")
        return "\n".join(lines)
    
    def _to_markdown(self, skill_data: dict) -> str:
        """转换为 markdown 格式"""
        lines = [
            "# 用户语气风格 (skill.md)",
            "",
            f"## {skill_data.get('skill_name', '用户风格')}",
            "",
            f"**一句话描述**: {skill_data.get('tldr', '普通聊天风格')}",
            "",
            "## 详细特征",
            "",
            f"**称呼习惯**: {skill_data.get('称呼习惯', '直接叫名字')}",
            f"**语气特征**: {skill_data.get('语气特征', '自然随和')}",
            f"**emoji使用**: {skill_data.get('emoji使用', '偶尔使用')}",
            f"**标点习惯**: {skill_data.get('标点习惯', '正常')}",
            "",
            "**常用词汇**:",
        ]
        
        words = skill_data.get('常用词汇', [])
        if words:
            for word in words[:10]:
                lines.append(f"- {word}")
        else:
            lines.append("- 普通词汇")
        
        lines.extend([
            "",
            "**话题偏好**:",
        ])
        
        topics = skill_data.get('话题偏好', [])
        if topics:
            for topic in topics[:5]:
                lines.append(f"- {topic}")
        else:
            lines.append("- 日常闲聊")
        
        lines.extend([
            "",
            "**回避事项**:",
        ])
        
        avoid = skill_data.get('回避事项', [])
        if avoid:
            for item in avoid[:3]:
                lines.append(f"- {item}")
        else:
            lines.append("- 无特殊偏好")
        
        lines.extend([
            "",
            "## 示例句子",
            "",
        ])
        
        examples = skill_data.get('示例句子', [])
        if examples:
            for ex in examples[:5]:
                lines.append(f"> {ex}")
        else:
            lines.append("> 好的！")
        
        return "\n".join(lines)
    
    def _default_skill_md(self) -> str:
        """默认 skill.md"""
        return """# 用户语气风格 (skill.md)

## 默认风格
**一句话描述**: 普通自然的聊天风格

## 详细特征

**称呼习惯**: 直接叫名字或小+姓
**语气特征**: 自然随和
**emoji使用**: 偶尔使用
**标点习惯**: 正常

**常用词汇**:
- 好的
- 没问题
- 哈哈

**话题偏好**:
- 日常闲聊
- 朋友互动

**回避事项**:
- 无特殊偏好

## 示例句子

> 好的！
> 没问题~
> 哈哈可以的
"""


# ============ 动态/频道检索服务 ============

class DynamicContentService:
    """步骤3：检索QQ动态、频道等相关数据"""
    
    def __init__(self, llm_service):
        self.llm = llm_service
    
    def search_relevant_content(self, user_interests: List[str], 
                                user_contacts: List[dict],
                                dynamics_data: dict = None,
                                ecosystem_data: dict = None) -> List[dict]:
        """
        基于用户兴趣检索相关内容
        
        Returns:
            相关内容列表，每项包含内容详情和关联的联系人
        """
        results = []
        
        # 搜索好友动态
        if dynamics_data:
            friend_dynamics = self._search_friend_dynamics(
                dynamics_data, user_interests, user_contacts
            )
            results.extend(friend_dynamics)
        
        # 搜索频道内容
        if ecosystem_data:
            channel_content = self._search_channel_content(
                ecosystem_data, user_interests
            )
            results.extend(channel_content)
        
        # 按相关度排序
        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return results[:10]  # 最多返回10条
    
    def _search_friend_dynamics(self, dynamics_data: dict, 
                                user_interests: List[str],
                                user_contacts: List[dict]) -> List[dict]:
        """搜索好友动态中与用户兴趣相关的内容"""
        results = []
        contact_map = {c.get("name", ""): c for c in user_contacts}
        
        for dyn in dynamics_data.get("dynamics", []):
            related_interests = dyn.get("related_interests", [])
            author = dyn.get("author", "")
            content = dyn.get("content", "")
            
            # 计算相关度
            interest_match = sum(1 for i in related_interests if i in user_interests)
            is_contact = author in contact_map
            
            if interest_match > 0 or is_contact:
                results.append({
                    "type": "friend_dynamic",
                    "author": author,
                    "content": content,
                    "related_interests": related_interests,
                    "interest_match": interest_match,
                    "is_contact": is_contact,
                    "contact_info": contact_map.get(author),
                    "relevance_score": interest_match + (1 if is_contact else 0),
                    "action_hint": self._generate_action_hint(dyn, is_contact)
                })
        
        return results
    
    def _search_channel_content(self, ecosystem_data: dict, 
                                user_interests: List[str]) -> List[dict]:
        """搜索频道内容"""
        results = []
        
        # QQ音乐
        for item in ecosystem_data.get("qqmusic", {}).get("recommendations", []):
            if any(tag.lower() in " ".join(user_interests).lower() 
                   for tag in item.get("tags", [])):
                results.append({
                    "type": "channel_recommendation",
                    "platform": "QQ音乐",
                    "content": item,
                    "relevance_score": len(item.get("tags", [])),
                    "action_hint": "发现你可能喜欢的音乐~"
                })
        
        # QQ阅读
        for item in ecosystem_data.get("qqreading", {}).get("recommendations", []):
            if any(tag.lower() in " ".join(user_interests).lower() 
                   for tag in item.get("tags", [])):
                results.append({
                    "type": "channel_recommendation",
                    "platform": "QQ阅读",
                    "content": item,
                    "relevance_score": len(item.get("tags", [])),
                    "action_hint": "推荐一本你可能喜欢的书~"
                })
        
        return results
    
    def _generate_action_hint(self, dynamic: dict, is_contact: bool) -> str:
        """生成行动提示"""
        author = dynamic.get("author", "好友")
        if is_contact:
            return f"你的好友{author}发布了新动态~"
        return f"发现{author}的动态，可能和你相关"


# ============ 消息监听服务 ============

class MessageListener:
    """步骤4：云端消息监听，自动更新图谱"""
    
    def __init__(self, graph_engine: GraphEngine, llm_service,
                 callback: Optional[callable] = None):
        self.graph = graph_engine
        self.llm = llm_service
        self.callback = callback  # 消息更新回调
        self.is_listening = False
        self.listener_thread = None
        self.last_message_time = None
        
        # 模拟消息队列（真实场景中来自 WebSocket 或轮询）
        self.message_queue: List[dict] = []
        self.message_lock = threading.Lock()
    
    def start_listening(self):
        """启动消息监听（后台线程）"""
        if self.is_listening:
            return
        
        self.is_listening = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()
        print("[MessageListener] 启动消息监听")
    
    def stop_listening(self):
        """停止消息监听"""
        self.is_listening = False
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        print("[MessageListener] 停止消息监听")
    
    def push_message(self, message: dict):
        """
        推送新消息到队列（真实场景中由 WebSocket/轮询调用）
        """
        with self.message_lock:
            self.message_queue.append(message)
    
    def _listen_loop(self):
        """监听循环"""
        while self.is_listening:
            try:
                # 处理消息队列
                messages_to_process = []
                with self.message_lock:
                    if self.message_queue:
                        messages_to_process = self.message_queue.copy()
                        self.message_queue.clear()
                
                for message in messages_to_process:
                    self._process_new_message(message)
                
                # 更新温度
                self.graph.update_temperatures()
                
                # 休眠一段时间
                time.sleep(5)  # 每5秒检查一次
                
            except Exception as e:
                print(f"[MessageListener] 监听异常: {e}")
                time.sleep(10)
    
    def _process_new_message(self, message: dict):
        """
        处理新消息：LLM分析 → 更新图谱 → 触发回调
        """
        try:
            # 获取当前图谱摘要
            current_graph = self.graph.get_graph_data()
            
            # LLM 分析消息
            analysis_result = self.llm.analyze_new_message(message, current_graph)
            
            action = analysis_result.get("action", "none")
            
            if action == "add_node":
                # 添加新节点
                node_data = analysis_result.get("node", {})
                node_data["id"] = node_data.get("id", f"msg_{int(time.time())}")
                result = self.graph.add_node_from_llm(node_data)
                
                if result.get("success"):
                    # 应用相关边
                    edge_data = analysis_result.get("edge", {})
                    if edge_data:
                        edge_data["target"] = result["node_id"]
                        self.graph.add_edge_from_llm(edge_data)
                    
                    # 触发回调
                    if self.callback:
                        self.callback({
                            "type": "node_added",
                            "node": node_data,
                            "message": message
                        })
            
            elif action == "update_node":
                # 更新现有节点
                node_data = analysis_result.get("node", {})
                self.graph.update_node_from_llm(node_data)
                
                if self.callback:
                    self.callback({
                        "type": "node_updated",
                        "node": node_data,
                        "message": message
                    })
            
            elif action == "delete_node":
                # 删除节点
                node_data = analysis_result.get("node", {})
                node_id = node_data.get("id")
                if node_id:
                    self.graph.delete_node(node_id)
                    
                    if self.callback:
                        self.callback({
                            "type": "node_deleted",
                            "node_id": node_id,
                            "message": message
                        })
            
            self.last_message_time = message.get("time")
            
        except Exception as e:
            print(f"[MessageListener] 处理消息失败: {e}")


# ============ Temperature 监控 + 主动拉起服务 ============

@dataclass
class AlertRule:
    """告警规则"""
    name: str
    threshold: float  # 温度阈值
    condition: str  # "below" | "above"
    priority: int = 1
    cooldown_minutes: int = 60  # 冷却时间（分钟）
    last_triggered: Optional[datetime] = None
    
    def can_trigger(self) -> bool:
        """检查是否可以触发"""
        if not self.last_triggered:
            return True
        elapsed = (datetime.now() - self.last_triggered).total_seconds() / 60
        return elapsed >= self.cooldown_minutes
    
    def mark_triggered(self):
        """标记已触发"""
        self.last_triggered = datetime.now()


class TemperatureMonitor:
    """步骤5：监控 Temperature，主动拉起用户"""
    
    def __init__(self, graph_engine: GraphEngine, llm_service,
                 alert_callback: Optional[callable] = None):
        self.graph = graph_engine
        self.llm = llm_service
        self.alert_callback = alert_callback  # 告警回调（用于闪亮提醒）
        
        # 初始化告警规则
        self.rules = [
            AlertRule(
                name="搭子降温预警",
                threshold=0.3,
                condition="below",
                priority=1,
                cooldown_minutes=120,
                rule_type="relationship_type",
                target_types=["搭子", "同好"]
            ),
            AlertRule(
                name="好友沉寂预警",
                threshold=0.4,
                condition="below",
                priority=2,
                cooldown_minutes=60,
                rule_type="relationship_type",
                target_types=["好友", "同学"]
            ),
            AlertRule(
                name="超低温紧急预警",
                threshold=0.15,
                condition="below",
                priority=0,
                cooldown_minutes=30
            ),
        ]
        
        self.alert_history: List[dict] = []
        self.is_monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self, interval_seconds: int = 300):
        """
        启动监控（后台线程）
        """
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            args=(interval_seconds,),
            daemon=True
        )
        self.monitor_thread.start()
        print(f"[TemperatureMonitor] 启动监控，间隔 {interval_seconds} 秒")
    
    def stop_monitoring(self):
        """停止监控"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        print("[TemperatureMonitor] 停止监控")
    
    def _monitor_loop(self, interval_seconds: int):
        """监控循环"""
        while self.is_monitoring:
            try:
                self.check_and_alert()
            except Exception as e:
                print(f"[TemperatureMonitor] 监控异常: {e}")
            
            time.sleep(interval_seconds)
    
    def check_and_alert(self) -> List[dict]:
        """
        检查温度并触发告警
        
        Returns:
            触发的告警列表
        """
        self.graph.update_temperatures()
        triggered_alerts = []
        
        for contact_id, contact in self.graph.contacts.items():
            temp = contact.temperature
            
            for rule in self.rules:
                if not rule.can_trigger():
                    continue
                
                should_alert = False
                if rule.condition == "below" and temp < rule.threshold:
                    # 检查类型匹配
                    if hasattr(rule, 'target_types'):
                        if contact.relationship_type not in rule.target_types:
                            continue
                    should_alert = True
                elif rule.condition == "above" and temp > rule.threshold:
                    should_alert = True
                
                if should_alert:
                    alert = self._create_alert(contact, rule)
                    triggered_alerts.append(alert)
                    rule.mark_triggered()
                    
                    # 触发回调
                    if self.alert_callback:
                        self.alert_callback(alert)
        
        return triggered_alerts
    
    def _create_alert(self, contact, rule: AlertRule) -> dict:
        """创建告警"""
        # 生成个性化提示
        greeting = self.llm.generate_greeting(
            contact_name=contact.name,
            relationship=contact.relationship_type,
            topic_context=contact.chat_history_summary or ", ".join(contact.tags),
            event_signal=f"已经{self._get_days_since(contact.last_interaction_time)}天没联系了"
        )
        
        alert = {
            "id": f"alert_{int(time.time())}_{contact.id}",
            "contact_id": contact.id,
            "contact_name": contact.name,
            "relationship_type": contact.relationship_type,
            "temperature": round(contact.temperature, 3),
            "rule_name": rule.name,
            "priority": rule.priority,
            "last_interaction": contact.last_interaction_time,
            "days_since": self._get_days_since(contact.last_interaction_time),
            "greeting_suggestion": greeting,
            "timestamp": datetime.now().isoformat(),
            "action_type": "pull_up"  # 主动拉起
        }
        
        self.alert_history.append(alert)
        return alert
    
    def _get_days_since(self, last_time_str: str) -> int:
        """计算距离上次互动多少天"""
        try:
            last_time = datetime.fromisoformat(last_time_str.replace('Z', '+00:00'))
            if last_time.tzinfo:
                last_time = last_time.replace(tzinfo=None)
            delta = datetime.now() - last_time
            return delta.days
        except:
            return 0
    
    def get_pending_alerts(self) -> List[dict]:
        """获取待处理的告警"""
        return self.alert_history[-10:]  # 最近10条
    
    def dismiss_alert(self, alert_id: str):
        """关闭告警"""
        self.alert_history = [a for a in self.alert_history if a.get("id") != alert_id]


# ============ 动态阈值调整服务 ============

@dataclass
class ThresholdConfig:
    """阈值配置"""
    name: str
    default_value: float
    current_value: float
    min_value: float = 0.1
    max_value: float = 1.0
    adjustment_history: List[dict] = field(default_factory=list)
    
    def adjust(self, direction: str, amount: float = 0.1):
        """调整阈值"""
        if direction == "up":
            self.current_value = min(self.max_value, self.current_value + amount)
        elif direction == "down":
            self.current_value = max(self.min_value, self.current_value - amount)
        
        self.adjustment_history.append({
            "timestamp": datetime.now().isoformat(),
            "direction": direction,
            "amount": amount,
            "new_value": self.current_value
        })


class ThresholdOptimizer:
    """步骤8：基于用户交互数据，动态调整阈值"""
    
    def __init__(self):
        # 初始化各场景阈值
        self.thresholds = {
            "cooling_detection": ThresholdConfig(
                name="搭子降温检测阈值",
                default_value=0.4,
                current_value=0.4
            ),
            "birthday_reminder_days": ThresholdConfig(
                name="生日提醒提前天数",
                default_value=7,
                current_value=7,
                min_value=1,
                max_value=14
            ),
            "activity_relevance": ThresholdConfig(
                name="动态相关性阈值",
                default_value=0.5,
                current_value=0.5
            ),
            "push_priority_high": ThresholdConfig(
                name="高优先级推送阈值",
                default_value=0.7,
                current_value=0.7
            ),
            "cold_node_threshold": ThresholdConfig(
                name="低温节点阈值",
                default_value=0.35,
                current_value=0.35
            ),
        }
        
        # 用户交互反馈
        self.feedback_data: List[dict] = []
    
    def record_feedback(self, card_type: str, action: str, 
                       interacted: bool, timestamp: datetime = None):
        """
        记录用户反馈
        
        Args:
            card_type: 卡片类型 (birthday_reminder, cooling_alert, etc.)
            action: 用户操作 (view, click, dismiss, ignore)
            interacted: 是否与卡片产生交互
        """
        feedback = {
            "card_type": card_type,
            "action": action,
            "interacted": interacted,
            "timestamp": (timestamp or datetime.now()).isoformat()
        }
        
        self.feedback_data.append(feedback)
        
        # 实时调整阈值
        self._adjust_based_on_feedback(card_type, action, interacted)
    
    def _adjust_based_on_feedback(self, card_type: str, action: str, 
                                  interacted: bool):
        """
        基于反馈调整阈值
        """
        if card_type == "cooling_alert":
            threshold = self.thresholds["cooling_detection"]
            
            if action == "click" or (action == "view" and interacted):
                # 用户感兴趣，降低阈值让更多搭子进入降温检测
                threshold.adjust("down", 0.05)
            elif action == "dismiss" or action == "ignore":
                # 用户不感兴趣，升高阈值减少推送
                threshold.adjust("up", 0.05)
        
        elif card_type == "birthday_reminder":
            threshold = self.thresholds["birthday_reminder_days"]
            
            if action == "click" or (action == "view" and interacted):
                # 用户重视生日提醒，增加提前天数
                threshold.adjust("up", 1)
            elif action == "dismiss":
                threshold.adjust("down", 1)
        
        elif card_type == "activity_recommendation":
            threshold = self.thresholds["activity_relevance"]
            
            if action == "click" or (action == "view" and interacted):
                threshold.adjust("down", 0.05)
            elif action == "dismiss":
                threshold.adjust("up", 0.05)
    
    def get_thresholds(self) -> dict:
        """获取当前阈值配置"""
        return {
            name: {
                "name": config.name,
                "current_value": config.current_value,
                "default_value": config.default_value,
                "adjustment_count": len(config.adjustment_history)
            }
            for name, config in self.thresholds.items()
        }
    
    def reset_thresholds(self):
        """重置所有阈值到默认值"""
        for config in self.thresholds.values():
            config.current_value = config.default_value
        print("[ThresholdOptimizer] 阈值已重置")


# ============ QBuddy 核心服务（整合所有模块） ============

class QBuddyService:
    """QBuddy 核心服务，整合所有功能模块"""
    
    def __init__(self, role: str, data_path: str = "./mock_data"):
        self.role = role
        self.data_path = data_path
        
        # 初始化各模块
        self.graph = GraphEngine()
        self.skill_extractor = UserSkillExtractor(llm_service)
        self.dynamic_service = DynamicContentService(llm_service)
        self.threshold_optimizer = ThresholdOptimizer()
        
        # 消息监听和温度监控（可选启动）
        self.message_listener: Optional[MessageListener] = None
        self.temp_monitor: Optional[TemperatureMonitor] = None
        
        # 用户 skill.md
        self.user_skill_md: Optional[str] = None
        
        # 数据缓存
        self._profile: Optional[dict] = None
        self._contacts: Optional[list] = None
        self._groups: Optional[dict] = None
        self._dynamics: Optional[dict] = None
        self._ecosystem: Optional[dict] = None
    
    # ============ 初始化方法 ============
    
    def initialize(self) -> dict:
        """
        初始化 QBuddy 服务
        执行步骤1-3：构建图谱、提取skill、分析动态
        """
        result = {
            "step1_graph": None,
            "step2_skill": None,
            "step3_dynamics": None
        }
        
        # 加载数据
        self._load_data()
        
        # 步骤1: 构建图谱
        result["step1_graph"] = self._build_graph()
        
        # 步骤2: 提取用户语气
        result["step2_skill"] = self._extract_user_skill()
        
        # 步骤3: 分析动态内容
        result["step3_dynamics"] = self._analyze_dynamics()
        
        return result
    
    def _load_data(self):
        """加载所有数据"""
        profile_path = f"{self.data_path}/{self.role}/profile.json"
        contacts_path = f"{self.data_path}/{self.role}/contacts.json"
        groups_path = f"{self.data_path}/{self.role}/groups.json"
        dynamics_path = f"{self.data_path}/{self.role}/dynamics.json"
        ecosystem_path = f"{self.data_path}/{self.role}/ecosystem.json"
        
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                self._profile = json.load(f)
        except: pass
        
        try:
            with open(contacts_path, "r", encoding="utf-8") as f:
                self._contacts = json.load(f).get("contacts", [])
        except: pass
        
        try:
            with open(groups_path, "r", encoding="utf-8") as f:
                self._groups = json.load(f)
        except: pass
        
        try:
            with open(dynamics_path, "r", encoding="utf-8") as f:
                self._dynamics = json.load(f)
        except: pass
        
        try:
            with open(ecosystem_path, "r", encoding="utf-8") as f:
                self._ecosystem = json.load(f)
        except: pass
    
    def _build_graph(self) -> dict:
        """步骤1: 使用 LLM 分析消息，构建图谱"""
        # 收集所有消息
        all_messages = []
        
        # 群聊消息
        if self._groups:
            for group in self._groups.get("groups", []):
                all_messages.extend(group.get("recent_messages", []))
        
        # 私聊消息（如果有）
        if self._contacts:
            for contact in self._contacts:
                private_msgs = contact.get("recent_messages", [])
                all_messages.extend(private_msgs)
        
        if all_messages:
            # LLM 分析
            role_name = self._profile.get("name", "我") if self._profile else "我"
            llm_result = llm_service.analyze_messages_for_graph(all_messages, role_name)
            
            # 应用到图谱
            apply_result = self.graph.apply_llm_result(llm_result)
            
            # 更新温度
            self.graph.update_temperatures()
            
            return {
                "llm_analysis": llm_result,
                "applied": apply_result,
                "graph_data": self.graph.get_graph_data()
            }
        
        # 降级：使用原有数据
        self.graph.load_data(self.role, self.data_path)
        self.graph.update_temperatures()
        return {"graph_data": self.graph.get_graph_data()}
    
    def _extract_user_skill(self) -> str:
        """步骤2: 从用户消息中提取语气风格"""
        # 收集用户消息
        user_messages = []
        
        if self._groups:
            for group in self._groups.get("groups", []):
                for msg in group.get("recent_messages", []):
                    # 假设消息来自用户本人（根据角色判断）
                    if msg.get("sender") in [self._profile.get("name", "")]:
                        user_messages.append(msg)
        
        self.user_skill_md = self.skill_extractor.extract_skill_from_messages(
            user_messages, self._profile
        )
        
        return self.user_skill_md
    
    def _analyze_dynamics(self) -> List[dict]:
        """步骤3: 检索相关动态内容"""
        if not self._dynamics and not self._ecosystem:
            return []
        
        user_interests = []
        if self._profile:
            user_interests = self._profile.get("persona", {}).get("interests", [])
        
        return self.dynamic_service.search_relevant_content(
            user_interests=user_interests,
            user_contacts=self._contacts or [],
            dynamics_data=self._dynamics,
            ecosystem_data=self._ecosystem
        )
    
    # ============ 启动后台服务 ============
    
    def start_background_services(self, 
                                  on_message: Optional[callable] = None,
                                  on_alert: Optional[callable] = None):
        """
        启动后台服务（步骤4、5）
        
        Args:
            on_message: 新消息回调
            on_alert: 告警回调（用于闪亮提醒）
        """
        # 步骤4: 启动消息监听
        self.message_listener = MessageListener(
            graph_engine=self.graph,
            llm_service=llm_service,
            callback=on_message
        )
        self.message_listener.start_listening()
        
        # 步骤5: 启动温度监控
        self.temp_monitor = TemperatureMonitor(
            graph_engine=self.graph,
            llm_service=llm_service,
            alert_callback=on_alert
        )
        self.temp_monitor.start_monitoring(interval_seconds=300)  # 5分钟检查一次
    
    def stop_background_services(self):
        """停止后台服务"""
        if self.message_listener:
            self.message_listener.stop_listening()
        if self.temp_monitor:
            self.temp_monitor.stop_monitoring()
    
    # ============ 推送生成 ============
    
    def generate_push_cards(self) -> List[dict]:
        """
        步骤6: 基于图谱数据生成聚合卡片
        """
        cards = []
        
        # 获取当前阈值
        cooling_threshold = self.threshold_optimizer.thresholds["cooling_detection"].current_value
        birthday_days = int(self.threshold_optimizer.thresholds["birthday_reminder_days"].current_value)
        
        # 1. 降温搭子卡片
        cold_contacts = [
            c for c in self.graph.contacts.values()
            if c.temperature < cooling_threshold and 
               c.relationship_type in ["搭子", "同好", "好友"]
        ]
        for contact in cold_contacts[:3]:
            greeting = llm_service.generate_greeting(
                contact_name=contact.name,
                relationship=contact.relationship_type,
                topic_context=contact.chat_history_summary,
                event_signal=f"好久没联系了"
            )
            cards.append({
                "type": "cooling_alert",
                "contact_id": contact.id,
                "name": contact.name,
                "relationship": contact.relationship_type,
                "temperature": round(contact.temperature, 3),
                "greeting_suggestion": greeting,
                "urgency": "high" if contact.temperature < 0.2 else "medium"
            })
        
        # 2. 生日提醒卡片
        if self._contacts:
            now = datetime.now()
            for contact in self._contacts:
                birthday_str = contact.get("birthday")
                if birthday_str:
                    try:
                        birthday = datetime.strptime(birthday_str, "%Y-%m-%d")
                        next_birthday = birthday.replace(year=now.year)
                        if next_birthday < now:
                            next_birthday = next_birthday.replace(year=now.year + 1)
                        
                        days_until = (next_birthday - now).days
                        
                        if 0 < days_until <= birthday_days:
                            blessing = llm_service.generate_blessing(
                                contact_name=contact.get("name", ""),
                                relationship=contact.get("relationship_type", ""),
                                chat_history=contact.get("chat_history_summary", "")
                            )
                            cards.append({
                                "type": "birthday_reminder",
                                "contact_id": contact.get("id"),
                                "name": contact.get("name"),
                                "days_until": days_until,
                                "personalized_blessing": blessing,
                                "urgency": "high" if days_until == 0 else "medium"
                            })
                    except: pass
        
        # 3. 动态推荐卡片
        if self._dynamics:
            for dyn in self._dynamics.get("dynamics", [])[:3]:
                cards.append({
                    "type": "activity_recommendation",
                    "author": dyn.get("author"),
                    "content": dyn.get("content", "")[:100],
                    "action_hint": dyn.get("action_hint", "发现新动态~")
                })
        
        return cards
    
    # ============ 对话服务 ============
    
    def chat(self, message: str) -> dict:
        """
        步骤7: QBuddy 对话服务 + Tool Calling
        """
        # 检查是否需要调用工具
        tool_result = self._check_tool_call(message)
        
        if tool_result.get("should_call"):
            # 执行工具调用
            return self._execute_tool_call(tool_result)
        
        # 普通对话
        return {
            "type": "chat",
            "response": self._generate_response(message),
            "skill_used": True
        }
    
    def _check_tool_call(self, message: str) -> dict:
        """检查是否需要调用工具"""
        prompt = f"""分析用户消息，判断是否需要调用工具。

用户消息：{message}

可用工具：
1. search_friends_dynamic - 搜索好友动态
2. search_channel_content - 搜索频道内容
3. get_contact_detail - 获取联系人详情
4. get_cold_contacts - 获取降温搭子
5. get_graph_data - 获取图谱数据

【输出格式】
{{"should_call": true/false, "tool_name": "工具名", "tool_args": {{...}}}}"""

        result = llm_service._call_llm([{"role": "user", "content": prompt}])
        
        if result:
            try:
                return json.loads(result)
            except:
                return {"should_call": False}
        
        return {"should_call": False}
    
    def _execute_tool_call(self, tool_info: dict) -> dict:
        """执行工具调用"""
        tool_name = tool_info.get("tool_name", "")
        tool_args = tool_info.get("tool_args", {})
        
        if tool_name == "search_friends_dynamic":
            interests = tool_args.get("interests", [])
            return {
                "type": "tool_result",
                "tool": tool_name,
                "result": self.dynamic_service.search_relevant_content(
                    user_interests=interests,
                    user_contacts=self._contacts or [],
                    dynamics_data=self._dynamics
                )
            }
        
        elif tool_name == "search_channel_content":
            interests = tool_args.get("interests", [])
            return {
                "type": "tool_result",
                "tool": tool_name,
                "result": self.dynamic_service.search_relevant_content(
                    user_interests=interests,
                    user_contacts=[],
                    ecosystem_data=self._ecosystem
                )
            }
        
        elif tool_name == "get_contact_detail":
            contact_id = tool_args.get("contact_id")
            return {
                "type": "tool_result",
                "tool": tool_name,
                "result": self.graph.get_contact_detail(contact_id)
            }
        
        elif tool_name == "get_cold_contacts":
            return {
                "type": "tool_result",
                "tool": tool_name,
                "result": self.graph.detect_cold_nodes()
            }
        
        elif tool_name == "get_graph_data":
            return {
                "type": "tool_result",
                "tool": tool_name,
                "result": self.graph.get_graph_data()
            }
        
        return {"type": "error", "message": "未知工具"}
    
    def _generate_response(self, message: str) -> str:
        """生成对话回复"""
        prompt = f"""你正在扮演 QBUDDY，一个智能社交助手。

用户skill.md：
{self.user_skill_md or '默认风格'}

用户说：{message}

请以 QBUDDY 的身份回复用户，风格友好、贴心。

直接返回回复内容，不要其他内容。"""

        result = llm_service._call_llm([
            {"role": "user", "content": prompt}
        ], temperature=0.8)
        
        return result.strip() if result else "你好！有什么我可以帮你的吗？"
    
    # ============ 反馈记录 ============
    
    def record_interaction(self, card_type: str, action: str, interacted: bool):
        """
        步骤8: 记录用户交互，用于调整阈值
        """
        self.threshold_optimizer.record_feedback(card_type, action, interacted)
    
    def get_threshold_config(self) -> dict:
        """获取阈值配置"""
        return self.threshold_optimizer.get_thresholds()


# ============ 全局服务实例管理 ============

# 存储当前活跃的服务实例
_active_services: Dict[str, QBuddyService] = {}


def get_or_create_service(role: str, data_path: str = "./mock_data") -> QBuddyService:
    """获取或创建服务实例"""
    if role not in _active_services:
        service = QBuddyService(role, data_path)
        service.initialize()
        _active_services[role] = service
    return _active_services[role]


def stop_all_services():
    """停止所有服务"""
    for service in _active_services.values():
        service.stop_background_services()
    _active_services.clear()

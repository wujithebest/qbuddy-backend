"""
6个核心场景检测器（新增请求+回复检测）
"""
import json
import random
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
from graph_engine import GraphEngine
from llm_service import llm_service

class ScenarioDetector:
    """场景检测器基类"""
    
    def __init__(self, graph_engine: GraphEngine):
        self.graph = graph_engine
        self.role = None
        self.profile = None
        self.groups = None
        
    def load_data(self, role: str, data_path: str = "./mock_data"):
        """加载数据"""
        self.role = role
        
        with open(f"{data_path}/{role}/profile.json", "r", encoding="utf-8") as f:
            self.profile = json.load(f)
            
        with open(f"{data_path}/{role}/groups.json", "r", encoding="utf-8") as f:
            self.groups = json.load(f)
            
        with open(f"{data_path}/{role}/contacts.json", "r", encoding="utf-8") as f:
            self.contacts_data = json.load(f)


class GroupMessageExtractor(ScenarioDetector):
    """场景1：群消息关键信息提取（支持 LLM 分析原始消息）"""
    
    def detect(self) -> List[dict]:
        """
        从群聊中提取 DDL、投票、@提醒
        优先使用 LLM 分析原始消息，fallback 到预设 type 字段
        """
        results = []
        
        for group in self.groups.get("groups", []):
            group_name = group.get("name", "")
            messages = group.get("recent_messages", [])
            
            # 方法1：使用 LLM 分析原始消息
            llm_results = self._extract_with_llm(messages, group_name)
            
            if llm_results:
                # 使用 LLM 分析结果
                for item in llm_results:
                    item["source_group"] = group_name
                    item["source_group_id"] = group.get("id")
                    item["scenario"] = "group_message_extraction"
                    item["action_required"] = self._get_action_hint(item.get("type", "normal"))
                    results.append(item)
            else:
                # 方法2：Fallback 到预设 type 字段
                for msg in messages:
                    msg_type = msg.get("type", "normal")
                    
                    if msg_type in ["announcement", "vote", "at_reminder"]:
                        item = {
                            "id": msg.get("id"),
                            "type": msg_type,
                            "content": msg.get("content"),
                            "sender": msg.get("sender"),
                            "time": msg.get("time"),
                            "source_group": group_name,
                            "source_group_id": group.get("id"),
                            "urgency": msg.get("urgency", "medium"),
                            "deadline": msg.get("deadline"),
                            "options": msg.get("options"),
                            "scenario": "group_message_extraction",
                            "action_required": self._get_action_hint(msg_type)
                        }
                        results.append(item)
        
        # 按紧迫程度排序
        urgency_order = {"high": 0, "medium": 1, "low": 2}
        results.sort(key=lambda x: urgency_order.get(x.get("urgency", "medium"), 1))
        
        return results
    
    def _extract_with_llm(self, messages: List[dict], group_name: str) -> List[dict]:
        """
        使用 LLM 从原始消息中提取关键信息
        将消息格式化为文本，发送给 LLM 分析
        """
        if not messages:
            return []
        
        # 将消息格式化为文本
        messages_text = self._format_messages_for_llm(messages)
        
        # 调用 LLM 分析
        try:
            llm_result = llm_service.extract_group_info(messages_text, group_name)
            
            if llm_result and "items" in llm_result:
                items = llm_result["items"]
                if isinstance(items, list) and len(items) > 0:
                    print(f"[GroupMessageExtractor] LLM 分析到 {len(items)} 条关键信息")
                    return items
        except Exception as e:
            print(f"[GroupMessageExtractor] LLM 分析失败: {e}")
        
        return []
    
    def _format_messages_for_llm(self, messages: List[dict]) -> str:
        """
        将消息列表格式化为 LLM 可读的文本
        保留发送者、内容和时间信息
        """
        lines = []
        for msg in messages:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            time_str = msg.get("time", "")
            
            # 简化时间格式
            if "T" in time_str:
                time_str = time_str.split("T")[1][:5] if "T" in time_str else time_str
            
            lines.append(f"[{time_str}] {sender}: {content}")
        
        return "\n".join(lines)
    
    def detect_with_llm(self, messages_text: str, group_name: str) -> dict:
        """使用LLM深度提取"""
        return llm_service.extract_group_info(messages_text)
    
    def _get_action_hint(self, msg_type: str) -> str:
        hints = {
            "announcement": "查看并确认",
            "vote": "请尽快投票",
            "at_reminder": "需要回复"
        }
        return hints.get(msg_type, "查看详情")


class BuddyCoolingDetector(ScenarioDetector):
    """场景2：搭子互动降温检测"""
    
    def detect(self) -> List[dict]:
        """检测降温中的搭子关系"""
        results = []
        NOW = datetime(2026, 5, 4, 20, 0, 0)
        
        for contact_id, contact in self.graph.contacts.items():
            # 搭子降温检测：支持兴趣搭子和工作搭子
            # college: 搭子/同好  young_worker: 同事/搭子  interest_focused: 画友/同好/同好圈老友
            if contact.relationship_type not in ["搭子", "同好", "同事", "前同事", "UI设计师", "画友", "高级PM", "同好圈老友"]:
                continue
            
            last_time = datetime.fromisoformat(
                contact.last_interaction_time.replace('Z', '+00:00')
            )
            if last_time.tzinfo:
                last_time = last_time.replace(tzinfo=None)
            
            current_interval = (NOW - last_time).total_seconds() / 3600
            threshold = contact.baseline_interval * 2.5
            
            # 降温信号：当前间隔超过基线的2.5倍
            if current_interval > threshold:
                # 计算降温程度
                cooling_ratio = current_interval / contact.baseline_interval
                
                result = {
                    "contact_id": contact_id,
                    "name": contact.name,
                    "relationship_type": contact.relationship_type,
                    "tags": contact.tags,
                    "last_interaction": contact.last_interaction_time,
                    "hours_since": round(current_interval, 1),
                    "baseline_interval": contact.baseline_interval,
                    "cooling_ratio": round(cooling_ratio, 2),
                    "temperature": round(contact.temperature, 3),
                    "urgency": "high" if cooling_ratio > 4 else "medium",
                    "scenario": "buddy_cooling",
                    "suggestion": self._generate_suggestion(contact, cooling_ratio),
                    "recent_events": contact.__dict__.get("recent_events", [])
                }
                results.append(result)
        
        # 按降温程度排序
        results.sort(key=lambda x: x["cooling_ratio"], reverse=True)
        return results
    
    def _generate_suggestion(self, contact, cooling_ratio: float) -> str:
        """生成建议"""
        if cooling_ratio > 5:
            return f"赶紧联系！已经{cooling_ratio:.1f}倍超基线了"
        elif cooling_ratio > 3:
            return "可以考虑约一下了"
        else:
            return "保持关注，可以主动聊聊"


class DormantReactivationDetector(ScenarioDetector):
    """场景3：沉寂关系重新激活"""
    
    def detect(self) -> List[dict]:
        """检测可以重新激活的沉寂关系"""
        results = []
        NOW = datetime(2026, 5, 4, 20, 0, 0)
        
        # 定义事件信号（支持大学生/职场人/插画师三种身份）
        event_signals = {
            # 大学生信号
            "考研出分": datetime(2026, 4, 20),
            "开学季": datetime(2026, 2, 20),
            "毕业季": datetime(2026, 6, 1),
            # 产品经理信号（小林）
            "新公司入职": datetime(2026, 4, 1),
            "晋升": datetime(2026, 5, 1),
            "项目完成": datetime(2026, 4, 28),
            # 插画师信号（小周）
            "插画展": datetime(2026, 5, 15),
            "新作品": datetime(2026, 5, 3),
            "约稿完成": datetime(2026, 5, 1),
        }
        
        for contact_id, contact in self.graph.contacts.items():
            # 检测条件1：静默超基线
            last_time = datetime.fromisoformat(
                contact.last_interaction_time.replace('Z', '+00:00')
            )
            if last_time.tzinfo:
                last_time = last_time.replace(tzinfo=None)
            
            current_interval = (NOW - last_time).total_seconds() / 3600
            
            if current_interval <= contact.baseline_interval:
                continue
            
            # 检测条件2：存在事件变化信号
            event_signal = self._check_event_signal(contact)
            
            if not event_signal:
                continue
            
            # 检测条件3：有前文话题
            topic_context = self._extract_topic_context(contact)
            
            if not topic_context:
                continue
            
            # 生成LLM开口建议
            greeting = llm_service.generate_greeting(
                contact_name=contact.name,
                relationship=contact.relationship_type,
                topic_context=topic_context,
                event_signal=event_signal
            )
            
            result = {
                "contact_id": contact_id,
                "name": contact.name,
                "relationship_type": contact.relationship_type,
                "chat_history_summary": contact.chat_history_summary,
                "last_interaction": contact.last_interaction_time,
                "hours_since": round(current_interval, 1),
                "temperature": round(contact.temperature, 3),
                "topic_context": topic_context,
                "event_signal": event_signal,
                "greeting_suggestion": greeting,
                "scenario": "dormant_reactivation",
                "urgency": "medium"
            }
            results.append(result)
        
        return results
    
    def _check_event_signal(self, contact) -> str:
        """检查事件变化信号"""
        recent_events = contact.__dict__.get("recent_events", [])
        
        if isinstance(recent_events, list):
            for event in recent_events:
                event_str = str(event)
                if "考研" in event_str and "出分" in event_str:
                    return "考研出分"
                if "生日" in event_str:
                    return "生日临近"
                if "入职" in event_str or "新公司" in event_str:
                    return "新公司入职"
                if "健身" in event_str or "运动" in event_str:
                    return "健身打卡"
                if "朋友圈" in event_str and ("上王者" in event_str or "游戏" in event_str):
                    return "游戏成就"
        
        return ""
    
    def _extract_topic_context(self, contact) -> str:
        """提取前文话题"""
        if contact.chat_history_summary:
            return contact.chat_history_summary
        if contact.tags:
            return "、".join(contact.tags)
        return ""


class ChannelRecommendationDetector(ScenarioDetector):
    """场景4：新爱好频道推荐"""
    
    # 频道标签映射
    CHANNEL_TAGS = {
        # 通用
        "技术探索": ["编程", "AI", "新技术", "程序员", "开发"],
        "校园音乐": ["音乐", "吉他", "弹唱", "乐队", "原创"],
        "摄影天地": ["摄影", "拍照", "后期", "相机", "构图"],
        "二次元": ["动漫", "二次元", "番剧", "漫展", "手办"],
        "游戏": ["游戏", "电竞", "开黑", "永劫", "王者"],
        "考研交流": ["考研", "复习", "上岸", "备考"],
        # 产品经理专属（小林）
        "互联网PM": ["产品经理", "PM", "PRD", "需求评审", "互联网"],
        "用户体验": ["用户体验", "UX", "交互设计", "用户研究", "调研"],
        "咖啡探店": ["咖啡", "探店", "生活", "办公"],
        "职场成长": ["职场", "职业发展", "晋升", "跳槽"],
        "播客资讯": ["播客", "知识", "深度阅读", "独立"],
        # 插画师专属（小周）
        "插画创作": ["插画", "绘画", "商稿", "Procreate", "数码绘画"],
        "胶片摄影": ["胶片", "相机", "暗房", "冲扫", "portra"],
        "手账文具": ["手账", "文具", "胶带", "MT", "素材"],
        "独立音乐": ["独立音乐", "民谣", "创作", "音乐人"],
    }
    
    def detect(self) -> List[dict]:
        """基于用户兴趣推荐频道内容"""
        user_interests = self.profile.get("persona", {}).get("interests", [])
        results = []
        
        for channel_name, tags in self.CHANNEL_TAGS.items():
            # 计算匹配度
            match_count = sum(1 for interest in user_interests 
                            for tag in tags if tag.lower() in interest.lower())
            
            if match_count > 0:
                results.append({
                    "channel_name": channel_name,
                    "matched_interests": [t for t in tags if any(
                        i.lower() in t.lower() or t.lower() in i.lower() 
                        for i in user_interests
                    )],
                    "match_score": match_count / len(tags),
                    "scenario": "channel_recommendation",
                    "suggestion": f"你在「{channel_name}」可能感兴趣的内容已更新"
                })
        
        # 按匹配度排序
        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results[:3]  # 返回top 3


class BirthdayReminderDetector(ScenarioDetector):
    """场景5：生日提醒 + 一键祝福"""
    
    def detect(self) -> List[dict]:
        """检测即将到来或已到的生日"""
        results = []
        NOW = date(2026, 5, 4)
        
        for contact in self.contacts_data.get("contacts", []):
            birthday_str = contact.get("birthday")
            if not birthday_str:
                continue
            
            try:
                birthday = datetime.strptime(birthday_str, "%Y-%m-%d").date()
                
                # 计算下一个生日
                next_birthday = birthday.replace(year=NOW.year)
                if next_birthday < NOW:
                    next_birthday = next_birthday.replace(year=NOW.year + 1)
                
                days_until = (next_birthday - NOW).days
                
                # 只提醒7天内的
                if days_until <= 7:
                    # 生成个性化祝福
                    blessing = llm_service.generate_blessing(
                        contact_name=contact["name"],
                        relationship=contact["relationship_type"],
                        chat_history=contact.get("chat_history_summary", ""),
                        birthday_type="birthday"
                    )
                    
                    result = {
                        "contact_id": contact["id"],
                        "name": contact["name"],
                        "relationship_type": contact["relationship_type"],
                        "birthday": birthday_str,
                        "next_birthday": next_birthday.isoformat(),
                        "days_until": days_until,
                        "is_today": days_until == 0,
                        "personalized_blessing": blessing,
                        "chat_history_summary": contact.get("chat_history_summary", ""),
                        "scenario": "birthday_reminder",
                        "urgency": "high" if days_until == 0 else "medium"
                    }
                    results.append(result)
                    
            except Exception as e:
                print(f"解析生日失败 {birthday_str}: {e}")
                continue
        
        # 按天数排序，今天的排最前
        results.sort(key=lambda x: x["days_until"])
        return results


class RequestResponseDetector(ScenarioDetector):
    """场景6：请求+回复关系检测（新增）"""
    
    # 接受的回复关键词
    ACCEPT_KEYWORDS = ['好', '可以', '行', '没问题', '收到', '好的', 'okay', 'ok', '嗯', '我来', '我帮你', '帮']
    
    # 请求关键词
    REQUEST_KEYWORDS = ['帮我', '帮我一下', '借我', '能帮我', '你可以帮我', '能不能', '帮个忙', '带', '拿', '帮我看看', '帮我下', '帮我下载']
    
    def detect(self) -> List[dict]:
        """检测请求+已答应 和 请求+未回复的场景"""
        results = []
        
        # 获取当前用户名
        role_name = self._get_role_name()
        
        for group in self.groups.get("groups", []):
            messages = group.get("recent_messages", [])
            
            # 分析消息序列
            for i, msg in enumerate(messages):
                content = msg.get("content", "")
                sender = msg.get("sender", "")
                msg_type = msg.get("type", "normal")
                target_user = msg.get("target_user", "")
                
                # 判断是否是发给当前用户的请求
                is_request = (
                    msg_type == "request" or 
                    (target_user and target_user in role_name) or
                    (self._is_request_message(content) and role_name in content)
                )
                
                if is_request and sender != role_name:
                    # 查找后续消息
                    later_messages = messages[i+1:i+6]
                    
                    # 检查是否已回复（接受或拒绝）
                    has_accepted = self._has_accepted_reply(later_messages, role_name)
                    has_replied = self._has_any_reply(later_messages, role_name)
                    
                    if has_accepted:
                        # 已答应的请求 - 提醒别忘了
                        result = {
                            "id": f"accepted_{msg.get('id')}",
                            "type": "accepted_request",
                            "content": content,
                            "sender": sender,
                            "time": msg.get("time"),
                            "source_group": group.get("name"),
                            "source_group_id": group.get("id"),
                            "urgency": "medium",
                            "scenario": "accepted_request",
                            "dialogue": self._generate_accepted_dialogue(sender, content),
                            "action_required": "记得帮忙哦"
                        }
                        results.append(result)
                    elif not has_replied:
                        # 未回复的请求 - 提示有人找你帮忙
                        result = {
                            "id": f"unreplied_{msg.get('id')}",
                            "type": "unreplied_request",
                            "content": content,
                            "sender": sender,
                            "time": msg.get("time"),
                            "source_group": group.get("name"),
                            "source_group_id": group.get("id"),
                            "urgency": "medium",
                            "scenario": "unreplied_request",
                            "dialogue": self._generate_unreplied_dialogue(sender, content),
                            "action_required": "回复一下"
                        }
                        results.append(result)
        
        return results
    
    def _get_role_name(self) -> str:
        """获取当前角色名"""
        if self.role == 'chen':
            return '小陈'
        elif self.role == 'lin':
            return '小林'
        elif self.role == 'zhou':
            return '小周'
        return '用户'
    
    def _is_request_message(self, content: str) -> bool:
        """判断是否是请求消息"""
        for keyword in self.REQUEST_KEYWORDS:
            if keyword in content:
                return True
        return False
    
    def _has_accepted_reply(self, later_messages: List[dict], role_name: str) -> bool:
        """检查是否有接受的回复"""
        for msg in later_messages:
            if msg.get("sender") == role_name:
                msg_type = msg.get("type", "normal")
                if msg_type == "accept":
                    return True
                
                content = msg.get("content", "").lower()
                for keyword in self.ACCEPT_KEYWORDS:
                    if keyword in content:
                        return True
        return False
    
    def _has_any_reply(self, later_messages: List[dict], role_name: str) -> bool:
        """检查是否有任何回复"""
        for msg in later_messages:
            if msg.get("sender") == role_name:
                return True
            msg_type = msg.get("type", "normal")
            if msg_type in ["accept", "normal", "at_reply"]:
                return True
        return False
    
    def _generate_accepted_dialogue(self, sender: str, content: str) -> str:
        """生成已答应请求的对话文本"""
        request_type = self._extract_request_type(content)
        
        dialogues = [
            f"小提醒~ {sender}让你帮忙{request_type}，你答应了的哦，别忘了~",
            f"嗨~ {sender}的请求你还没忘吧？{request_type}这件事~",
            f"注意啦！{sender}的忙你答应帮的，别鸽了哦~"
        ]
        
        return random.choice(dialogues)
    
    def _generate_unreplied_dialogue(self, sender: str, content: str) -> str:
        """生成未回复请求的对话文本"""
        dialogues = [
            f"{sender}在找你帮忙呢~ {content}",
            f"嘿！{sender}让你帮忙，有点急哦~有空回复一下？",
            f"小提示：{sender}给你发消息了，还没看到吗？"
        ]
        
        return random.choice(dialogues)
    
    def _extract_request_type(self, content: str) -> str:
        """提取请求类型"""
        if '带饭' in content or ('带' in content and '饭' in content):
            return '带饭'
        elif '借' in content:
            return '借东西'
        elif '看' in content:
            return '看看'
        elif '下' in content or '下载' in content:
            return '下载'
        elif '拍' in content:
            return '拍照'
        elif '笔记' in content:
            return '借笔记'
        else:
            return '帮忙'


class ScenarioDetectorManager:
    """场景检测管理器"""
    
    def __init__(self, graph_engine: GraphEngine):
        self.graph = graph_engine
        self.extractor = GroupMessageExtractor(graph_engine)
        self.cooling_detector = BuddyCoolingDetector(graph_engine)
        self.reactivation_detector = DormantReactivationDetector(graph_engine)
        self.channel_detector = ChannelRecommendationDetector(graph_engine)
        self.birthday_detector = BirthdayReminderDetector(graph_engine)
        self.request_detector = RequestResponseDetector(graph_engine)  # 新增
    
    def load_data(self, role: str, data_path: str = "./mock_data"):
        """加载所有检测器的数据"""
        self.extractor.load_data(role, data_path)
        self.cooling_detector.load_data(role, data_path)
        self.reactivation_detector.load_data(role, data_path)
        self.channel_detector.load_data(role, data_path)
        self.birthday_detector.load_data(role, data_path)
        self.request_detector.load_data(role, data_path)  # 新增
    
    def run_all_detections(self) -> dict:
        """运行所有场景检测"""
        return {
            "group_messages": self.extractor.detect(),
            "buddy_cooling": self.cooling_detector.detect(),
            "dormant_reactivation": self.reactivation_detector.detect(),
            "channel_recommendations": self.channel_detector.detect(),
            "birthday_reminders": self.birthday_detector.detect(),
            "request_response": self.request_detector.detect()  # 新增
        }
    
    def get_prioritized_alerts(self) -> List[dict]:
        """获取优先级排序的提醒"""
        all_results = self.run_all_detections()
        alerts = []
        
        # 重组为统一格式
        for category, items in all_results.items():
            for item in items:
                item["category"] = category
                item["priority"] = self._calculate_priority(item)
                alerts.append(item)
        
        # 按优先级排序
        alerts.sort(key=lambda x: x["priority"], reverse=True)
        return alerts[:10]
    
    def _calculate_priority(self, item: dict) -> float:
        """计算优先级分数"""
        priority = 0.0
        
        # 紧迫程度
        urgency_scores = {"high": 3.0, "medium": 2.0, "low": 1.0}
        priority += urgency_scores.get(item.get("urgency", "medium"), 1.5)
        
        # 场景类型加成
        if item.get("scenario") == "birthday_reminder" and item.get("is_today"):
            priority += 2.0
        elif item.get("scenario") == "buddy_cooling":
            priority += 1.5
        elif item.get("scenario") == "group_message_extraction":
            priority += 1.0
        elif item.get("scenario") in ["accepted_request", "unreplied_request"]:
            priority += 1.2  # 新增请求场景的优先级加成
        
        # 温度加成（低温关系激活优先级更高）
        if "temperature" in item:
            priority += (1.0 - item["temperature"]) * 0.5
        
        return round(priority, 2)

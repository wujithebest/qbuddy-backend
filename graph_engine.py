"""
关系增强图谱引擎
实现温度计算、节点管理和图谱操作
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

@dataclass
class Contact:
    id: str
    name: str
    relationship_type: str
    tags: List[str]
    last_interaction_time: str
    baseline_interval: float
    birthday: Optional[str]
    chat_history_summary: str
    interest_tags: List[str]
    temperature: float = 0.5
    recent_events: List[str] = None  # 额外字段
    
    # 温度计算参数
    decay_rate: float = 0.01  # 默认衰减系数
    
    def __post_init__(self):
        if self.recent_events is None:
            self.recent_events = []
        # 根据关系类型设置衰减系数
        decay_rates = {
            # 大学生
            "搭子": 0.015,
            "同好": 0.012,
            "好友": 0.008,
            "同学": 0.010,
            "室友": 0.018,
            "家人": 0.005,
            "群成员": 0.006,
            # 职场人（产品经理）
            "同事": 0.010,
            "前同事": 0.015,
            "产品总监": 0.005,
            "高级PM": 0.008,
            "UI设计师": 0.012,
            "后端开发": 0.010,
            "HR": 0.020,
            # 插画师
            "画友": 0.012,
            "摄影圈好友": 0.012,
            "房东": 0.030,
            "编辑": 0.008,
            "甲方": 0.015,
            "独立音乐人": 0.012,
            "同好圈老友": 0.010,
            "画廊策展人": 0.020,
        }
        self.decay_rate = decay_rates.get(self.relationship_type, 0.01)

@dataclass
class Edge:
    source: str
    target: str
    weight: float
    temperature: float
    edge_type: str
    cooling_ratio: Optional[float] = None  # 来自edges数据的额外字段
    days_since_interaction: Optional[int] = None

@dataclass
class Interaction:
    timestamp: str
    type: str  # message/call/game/event
    emotion_score: float  # 0-1, 情绪强度
    content_preview: str

class GraphEngine:
    """关系增强图谱引擎"""
    
    # 当前时间（用于计算）
    NOW = datetime(2026, 5, 4, 20, 0, 0)  # Demo演示时间
    
    def __init__(self):
        self.contacts: Dict[str, Contact] = {}
        self.edges: Dict[str, Edge] = {}
        self.interactions: Dict[str, List[Interaction]] = {}
        
    def load_data(self, role: str, data_path: str = "./mock_data"):
        """加载角色数据"""
        # 加载联系人
        with open(f"{data_path}/{role}/contacts.json", "r", encoding="utf-8") as f:
            contacts_data = json.load(f)
        
        for contact_data in contacts_data["contacts"]:
            contact = Contact(**contact_data)
            self.contacts[contact.id] = contact
        
        # 加载边（如果存在edges字段则使用，否则从contacts自动构建）
        edges_data = contacts_data.get("edges", [])
        if not edges_data:
            # 从contacts自动构建edges
            for contact in self.contacts.values():
                key = f"user->{contact.id}"
                self.edges[key] = Edge(
                    source="user",
                    target=contact.id,
                    weight=0.5 + contact.temperature * 0.5,
                    temperature=contact.temperature,
                    edge_type=contact.relationship_type
                )
        else:
            for edge_data in edges_data:
                edge = Edge(**edge_data)
                key = f"{edge.source}->{edge.target}"
                self.edges[key] = edge
    
    def calculate_temperature(self, contact_id: str) -> Tuple[float, dict]:
        """
        计算当前温度值
        T(i,j,t) = Σ(k=1→N) w_k × f(type_k) × e^(-λ·Δt_k)
        
        返回: (温度值, 计算过程详情)
        """
        contact = self.contacts.get(contact_id)
        if not contact:
            return 0.0, {}
        
        last_time = datetime.fromisoformat(contact.last_interaction_time.replace('Z', '+00:00'))
        # 如果是带时区的，去掉时区信息
        if last_time.tzinfo:
            last_time = last_time.replace(tzinfo=None)
        
        delta_hours = (self.NOW - last_time).total_seconds() / 3600
        
        # 基础衰减
        base_temp = 1.0 * (2.71828 ** (-contact.decay_rate * delta_hours))
        
        # 交互类型权重（简化版，根据baseline调整）
        interval_ratio = delta_hours / contact.baseline_interval if contact.baseline_interval > 0 else 1
        
        # 温度过低时给予惩罚
        if interval_ratio > 2.5:
            base_temp *= 0.5
        
        temperature = max(0.0, min(1.0, base_temp))
        
        calc_detail = {
            "last_interaction": contact.last_interaction_time,
            "hours_since": round(delta_hours, 1),
            "baseline_interval": contact.baseline_interval,
            "interval_ratio": round(interval_ratio, 2),
            "decay_rate": contact.decay_rate,
            "temperature": round(temperature, 3)
        }
        
        return temperature, calc_detail
    
    def update_temperatures(self):
        """更新所有联系人的温度值"""
        for contact_id in self.contacts:
            temp, _ = self.calculate_temperature(contact_id)
            self.contacts[contact_id].temperature = temp
            
        # 更新边的温度
        for key, edge in self.edges.items():
            target_id = edge.target
            if target_id in self.contacts:
                edge.temperature = self.contacts[target_id].temperature
    
    def detect_cold_nodes(self, threshold: float = 0.4) -> List[dict]:
        """检测低温节点"""
        self.update_temperatures()
        cold_nodes = []
        
        for contact_id, contact in self.contacts.items():
            if contact.temperature < threshold:
                temp, calc_detail = self.calculate_temperature(contact_id)
                cold_nodes.append({
                    "contact_id": contact_id,
                    "name": contact.name,
                    "temperature": round(contact.temperature, 3),
                    "relationship_type": contact.relationship_type,
                    "last_interaction": contact.last_interaction_time,
                    "hours_since": calc_detail.get("hours_since", 0),
                    "baseline_interval": contact.baseline_interval,
                    "urgency": "high" if contact.temperature < 0.25 else "medium"
                })
        
        # 按温度排序，最冷的排在前面
        cold_nodes.sort(key=lambda x: x["temperature"])
        return cold_nodes
    
    def get_graph_data(self, highlight_nodes: List[str] = None) -> dict:
        """
        获取D3.js可视化的图谱数据
        返回nodes + links格式
        """
        self.update_temperatures()
        highlight_set = set(highlight_nodes or [])
        
        nodes = []
        for contact_id, contact in self.contacts.items():
            node = {
                "id": contact_id,
                "name": contact.name,
                "group": self._get_group_id(contact.relationship_type),
                "temperature": round(contact.temperature, 3),
                "relationship_type": contact.relationship_type,
                "tags": contact.tags,
                "is_highlighted": contact_id in highlight_set,
                "birthday": contact.birthday,
                "baseline_interval": contact.baseline_interval,
                "last_interaction": contact.last_interaction_time,
                "color": "#4A6CF7"  # 非用户节点统一蓝色
            }
            nodes.append(node)
        
        # 添加中心用户节点
        nodes.insert(0, {
            "id": "user",
            "name": "我",
            "group": 0,
            "temperature": 1.0,
            "color": "#2D4AE0"  # 用户节点深蓝
        })
        
        links = []
        for key, edge in self.edges.items():
            links.append({
                "source": edge.source,
                "target": edge.target,
                "weight": edge.weight,
                "temperature": round(edge.temperature, 3),
                "type": edge.edge_type,
                "is_highlighted": edge.target in highlight_set
            })
        
        return {
            "nodes": nodes,
            "links": links,
            "stats": {
                "total_nodes": len(nodes),
                "total_links": len(links),
                "avg_temperature": round(sum(n["temperature"] for n in nodes) / len(nodes), 3)
            }
        }
    
    def _get_group_id(self, relationship_type: str) -> int:
        """根据关系类型返回分组ID"""
        groups = {
            "self": 0,
            "家人": 1,
            "搭子": 2,
            "同好": 3,
            "室友": 4,
            "同学": 5,
            "好友": 6,
            "群成员": 7
        }
        return groups.get(relationship_type, 6)
    
    def get_contact_detail(self, contact_id: str) -> Optional[dict]:
        """获取联系人详情"""
        contact = self.contacts.get(contact_id)
        if not contact:
            return None
        
        temp, calc_detail = self.calculate_temperature(contact_id)
        
        return {
            "id": contact.id,
            "name": contact.name,
            "relationship_type": contact.relationship_type,
            "tags": contact.tags,
            "interest_tags": contact.interest_tags,
            "chat_history_summary": contact.chat_history_summary,
            "temperature": round(temp, 3),
            "temperature_detail": calc_detail,
            "last_interaction_time": contact.last_interaction_time,
            "birthday": contact.birthday,
            "baseline_interval": contact.baseline_interval,
            "temperature_status": self._get_temperature_status(temp)
        }
    
    def _get_temperature_status(self, temp: float) -> str:
        """获取温度状态描述"""
        if temp >= 0.8:
            return "火热 🔥"
        elif temp >= 0.6:
            return "温暖 ☀️"
        elif temp >= 0.4:
            return "一般 😐"
        elif temp >= 0.2:
            return "冷淡 ❄️"
        else:
            return "冰冷 🧊"
    
    # ============ LLM 增量更新方法 ============
    
    def add_node_from_llm(self, node_data: dict) -> dict:
        """
        从 LLM 分析结果添加新节点
        
        Args:
            node_data: {
                "id": "person_1",
                "name": "小王",
                "type": "contact|event",
                "properties": {...},
                "urgency": "high/medium/low",
                "action_hint": "需要的行动"
            }
        
        Returns:
            添加成功返回节点信息，失败返回错误
        """
        try:
            node_id = node_data.get("id", f"llm_node_{len(self.contacts)}")
            node_type = node_data.get("type", "contact")
            
            if node_type == "contact":
                # 添加联系人节点
                properties = node_data.get("properties", {})
                
                contact = Contact(
                    id=node_id,
                    name=node_data.get("name", "未知"),
                    relationship_type=properties.get("identity", "群友"),
                    tags=properties.get("tags", []),
                    last_interaction_time=self.NOW.isoformat(),
                    baseline_interval=72.0,  # 默认3天
                    birthday=None,
                    chat_history_summary="",
                    interest_tags=properties.get("interests", []),
                    temperature=0.7  # 新节点默认温度较高
                )
                self.contacts[node_id] = contact
                
                # 自动添加与用户的边
                edge_key = f"user->{node_id}"
                self.edges[edge_key] = Edge(
                    source="user",
                    target=node_id,
                    weight=0.6,
                    temperature=0.7,
                    edge_type=properties.get("identity", "群友")
                )
                
                return {
                    "success": True,
                    "node_id": node_id,
                    "type": "contact",
                    "urgency": node_data.get("urgency", "medium")
                }
            
            elif node_type == "event":
                # 添加事件节点（存储为特殊联系人或独立存储）
                # 这里简化处理，将事件节点添加到 contacts 中，标记为 event 类型
                event_contact = Contact(
                    id=node_id,
                    name=node_data.get("name", "事件"),
                    relationship_type="event",
                    tags=node_data.get("properties", {}).get("tags", []),
                    last_interaction_time=self.NOW.isoformat(),
                    baseline_interval=24.0,  # 事件默认1天有效期
                    birthday=None,
                    chat_history_summary=node_data.get("action_hint", ""),
                    interest_tags=[],
                    temperature=0.9  # 新事件高优先级
                )
                self.contacts[node_id] = event_contact
                
                return {
                    "success": True,
                    "node_id": node_id,
                    "type": "event",
                    "urgency": node_data.get("urgency", "high")
                }
            
            return {"success": False, "error": "未知节点类型"}
        
        except Exception as e:
            print(f"[GraphEngine] 添加节点失败: {e}")
            return {"success": False, "error": str(e)}
    
    def update_node_from_llm(self, node_data: dict) -> dict:
        """
        从 LLM 分析结果更新现有节点
        """
        node_id = node_data.get("id")
        if not node_id or node_id not in self.contacts:
            return {"success": False, "error": "节点不存在"}
        
        try:
            contact = self.contacts[node_id]
            
            # 更新属性
            properties = node_data.get("properties", {})
            if "identity" in properties:
                contact.relationship_type = properties["identity"]
            if "tags" in properties:
                contact.tags = properties["tags"]
            if "personality" in properties:
                contact.chat_history_summary = properties["personality"]
            if "interests" in properties:
                contact.interest_tags = properties["interests"]
            
            return {
                "success": True,
                "node_id": node_id,
                "type": contact.relationship_type
            }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_node(self, node_id: str) -> dict:
        """删除节点"""
        if node_id not in self.contacts:
            return {"success": False, "error": "节点不存在"}
        
        try:
            # 删除节点
            del self.contacts[node_id]
            
            # 删除相关边
            edges_to_delete = [k for k in self.edges.keys() 
                             if node_id in k]
            for key in edges_to_delete:
                del self.edges[key]
            
            return {"success": True, "node_id": node_id}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def add_edge_from_llm(self, edge_data: dict) -> dict:
        """
        从 LLM 分析结果添加边
        """
        try:
            source = edge_data.get("source", "user")
            target = edge_data.get("target")
            
            if not target:
                return {"success": False, "error": "缺少目标节点"}
            
            edge_key = f"{source}->{target}"
            
            if edge_key in self.edges:
                # 边已存在，更新权重
                self.edges[edge_key].weight = edge_data.get("strength", 0.5)
                return {"success": True, "edge_key": edge_key, "action": "updated"}
            
            # 创建新边
            self.edges[edge_key] = Edge(
                source=source,
                target=target,
                weight=edge_data.get("strength", 0.5),
                temperature=edge_data.get("strength", 0.5),
                edge_type=edge_data.get("relationship", "群友")
            )
            
            return {"success": True, "edge_key": edge_key, "action": "created"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def apply_llm_result(self, llm_result: dict) -> dict:
        """
        应用完整的 LLM 分析结果到图谱
        
        Args:
            llm_result: {
                "nodes_to_add": [...],
                "nodes_to_update": [...],
                "nodes_to_delete": [...],
                "edges_to_add": [...],
                "tags": [...],
                "summary": "..."
            }
        
        Returns:
            应用结果统计
        """
        result = {
            "nodes_added": 0,
            "nodes_updated": 0,
            "nodes_deleted": 0,
            "edges_added": 0,
            "tags": llm_result.get("tags", []),
            "summary": llm_result.get("summary", ""),
            "alerts": []  # 需要推送的提醒
        }
        
        # 添加节点
        for node_data in llm_result.get("nodes_to_add", []):
            add_result = self.add_node_from_llm(node_data)
            if add_result.get("success"):
                result["nodes_added"] += 1
                # 如果是高优先级，添加提醒
                if add_result.get("urgency") == "high":
                    result["alerts"].append({
                        "type": "new_node",
                        "node": node_data,
                        "action": add_result
                    })
        
        # 更新节点
        for node_data in llm_result.get("nodes_to_update", []):
            update_result = self.update_node_from_llm(node_data)
            if update_result.get("success"):
                result["nodes_updated"] += 1
        
        # 删除节点
        for node_data in llm_result.get("nodes_to_delete", []):
            node_id = node_data.get("id")
            if node_id:
                delete_result = self.delete_node(node_id)
                if delete_result.get("success"):
                    result["nodes_deleted"] += 1
        
        # 添加边
        for edge_data in llm_result.get("edges_to_add", []):
            edge_result = self.add_edge_from_llm(edge_data)
            if edge_result.get("success"):
                result["edges_added"] += 1
        
        return result

"""
QBuddy Flask后端
提供REST API支持前端调用
包含对话式助手功能
"""
import os
import json
import time
import random
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

from graph_engine import GraphEngine
from scenario_detector import ScenarioDetectorManager
from llm_service import llm_service

load_dotenv()

app = Flask(__name__)
CORS(app)

# 访问密码
ACCESS_PASSWORD = os.environ.get('ACCESS_PASSWORD', 'qbuddy2026')

# 全局状态
current_role = None
graph_engine = None
detector_manager = None

# 数据路径
DATA_PATH = os.path.join(os.path.dirname(__file__), "mock_data")


def require_password(f):
    """密码验证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('X-Access-Password')
        password = auth_header or request.args.get('password')
        
        if password != ACCESS_PASSWORD:
            return jsonify({"error": "Unauthorized", "message": "Invalid access password"}), 401
        
        return f(*args, **kwargs)
    return decorated


def success_response(data, message="Success"):
    """统一成功响应格式"""
    return jsonify({
        "code": 200,
        "message": message,
        "data": data,
        "timestamp": datetime.now().isoformat()
    })


def error_response(message, code=400):
    """统一错误响应格式"""
    return jsonify({
        "code": code,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }), code


# ============ 认证相关 ============

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({"status": "ok", "service": "qb-api"}), 200


@app.route('/api/test-llm', methods=['GET'])
@require_password
def test_llm():
    """测试 LLM API 是否正常工作"""
    try:
        test_result = llm_service._call_llm([
            {"role": "user", "content": "你好，回复1+1=?"}
        ], temperature=0.3, max_tokens=100)
        
        if test_result:
            return success_response({
                "success": True,
                "model": llm_service.model,
                "response": test_result
            })
        else:
            return error_response("LLM 调用失败", 500)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(f"测试失败: {str(e)}", 500)


@app.route('/api/auth/verify', methods=['POST'])
def verify_password():
    """验证访问密码"""
    data = request.get_json() or {}
    password = data.get('password', '')
    
    if password == ACCESS_PASSWORD:
        return success_response({"valid": True, "token": "qb_2026_token"})
    else:
        return error_response("Invalid password", 401)


# ============ 自定义角色生成 ============

@app.route('/api/customize/generate', methods=['POST'])
@require_password
def generate_custom_role():
    """
    基于用户选择生成自定义角色数据
    identity: college(大学生) | young_worker(工作年轻人) | interest_focused(兴趣领域)
    """
    data = request.get_json() or {}
    
    identity = data.get('identity', 'college')  # 身份类型
    name = data.get('name', '自定义用户')
    interests = data.get('interests', [])
    pain_focus = data.get('painFocus', [])
    info_density = data.get('infoDensity', 'normal')
    social_style = data.get('socialStyle', 'moderate')
    major = data.get('major', '')
    
    try:
        # 根据identity生成差异化数据
        if identity == 'college':
            role_data = _generate_college_role(name, interests, pain_focus, info_density, major)
        elif identity == 'young_worker':
            role_data = _generate_worker_role(name, interests, pain_focus, info_density, major)
        elif identity == 'interest_focused':
            role_data = _generate_interest_role(name, interests, pain_focus, info_density, major)
        else:
            role_data = _generate_college_role(name, interests, pain_focus, info_density, major)
        
        # 生成唯一ID
        role_id = f"custom_{int(time.time())}"
        role_data['id'] = role_id
        
        return success_response(role_data, "角色生成成功")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(f"角色生成失败: {str(e)}", 500)


def _generate_college_role(name, interests, pain_focus, info_density, major):
    """大学生角色模板 - 好友少但关系紧密"""
    # 兴趣映射
    interest_emoji = {
        'gaming': '🎮', 'anime': '🎭', 'music': '🎵', 'sports': '⚽',
        'reading': '📚', 'food': '🍜', 'coding': '💻', 'travel': '✈️'
    }
    
    # 基础设置
    base_friends = 5 if info_density == 'overload' else 6
    base_groups = 4 if info_density == 'overload' else 3
    
    # 生成联系人 - 以搭子和同学为主
    contacts = [
        {
            'id': f'contact_{i}',
            'name': f'搭子{i}' if i < 2 else f'同学{i-1}',
            'interest_tags': [interests[0]] if interests else ['gaming'],
            'relationship_type': '搭子' if i < 2 else ('室友' if i == 2 else '同学'),
            'baseline_interval': 3,
            'last_interaction_time': _days_ago(19 if i < 2 else 5),
            'chat_history_summary': '最近在讨论' + ('游戏新赛季' if i == 0 else ('考研复习进度' if i == 1 else '课程作业')),
            'group_id': 1 if i < 2 else 2,
            'temperature': 0.25 if i < 2 else 0.65
        }
        for i in range(base_friends)
    ]
    
    # 老师/助教
    contacts.extend([
        {
            'id': 'contact_ta',
            'name': '助教小王',
            'interest_tags': ['coding'],
            'relationship_type': '老师',
            'baseline_interval': 7,
            'last_interaction_time': _days_ago(2),
            'chat_history_summary': '发布课程通知',
            'group_id': 3,
            'temperature': 0.8
        }
    ])
    
    # 生成群聊 - 课程群、项目群为主
    groups = [
        {
            'name': '数据库课程群',
            'recent_messages': [
                {'sender': '助教小王', 'content': '【重要】数据库实验报告DDL提前到5月6日中午12点！不是5月8日了！', 'time': '08:00', 'type': 'announcement'},
                {'sender': '小张', 'content': '啊？？提前了？？我还没开始写呢😭', 'time': '08:01', 'type': 'text'},
                {'sender': '小李', 'content': '救命 论文还没写完又要赶实验报告', 'time': '08:02', 'type': 'text'},
            ]
        },
        {
            'name': '操作系统课程群',
            'recent_messages': [
                {'sender': '助教张老师', 'content': '【重要】下周三之前提交OS实验报告', 'time': '20:00', 'type': 'announcement'},
                {'sender': '小赵', 'content': '收到', 'time': '20:01', 'type': 'text'},
            ]
        },
        {
            'name': '班级群',
            'recent_messages': [
                {'sender': '辅导员', 'content': '@全体成员 下周一之前交学年鉴定表', 'time': '10:00', 'type': 'announcement'},
            ]
        },
        {
            'name': '算法讨论群',
            'recent_messages': [
                {'sender': '小王', 'content': '这个解法不太对吧', 'time': '10:30', 'type': 'text'},
                {'sender': '小陈', 'content': '为啥不对 我觉得可以啊', 'time': '10:31', 'type': 'text'},
            ]
        }
    ]
    
    # 只取前base_groups个群
    groups = groups[:base_groups]
    
    # 痛点
    pain_points = []
    if 'missed_ddl' in pain_focus:
        pain_points.append('课程群消息太多，DDL总是淹没在闲聊里')
    if 'buddy_cooling' in pain_focus:
        pain_points.append('游戏搭子好久没一起打了，关系在降温')
    if 'missed_birthday' in pain_focus:
        pain_points.append('朋友太多，生日总是记不住')
    if 'vote' in pain_focus:
        pain_points.append('投票经常错过，被@也看不到')
    
    # 构建图谱数据
    graph_nodes = [
        {'id': 'user', 'name': name, 'type': 'user', 'group': 0}
    ]
    graph_links = []
    
    for c in contacts:
        graph_nodes.append({
            'id': c['id'],
            'name': c['name'],
            'type': 'contact',
            'group': c['group_id'],
            'weight': c['temperature'],
            'relationship_type': c['relationship_type']
        })
        graph_links.append({
            'source': 'user',
            'target': c['id'],
            'strength': c['temperature'],
            'temp': 'cooling' if c['temperature'] < 0.4 else 'normal'
        })
    
    # 添加事件节点
    if 'missed_ddl' in pain_focus:
        graph_nodes.append({
            'id': 'event_ddl',
            'name': '数据库实验报告DDL',
            'type': 'event',
            'eventType': 'ddl'
        })
        graph_links.append({
            'source': 'event_ddl',
            'target': 'contact_ta',
            'strength': 0.9,
            'temp': 'hot'
        })
    
    return {
        'name': name,
        'grade': '大三' if not major else '',
        'major': major or '计算机科学与技术',
        'bio': '课业繁重的技术宅，群消息99+是常态',
        'painPoints': pain_points,
        'interests': interests,
        'contacts': {'contacts': contacts},
        'groups': {'groups': groups},
        'graph': {'nodes': graph_nodes, 'links': graph_links}
    }


def _generate_worker_role(name, interests, pain_focus, info_density, major):
    """工作年轻人角色模板 - 好友中等，同事和前同学为主"""
    interest_emoji = {
        'gaming': '🎮', 'music': '🎵', 'sports': '⚽',
        'reading': '📚', 'food': '🍜', 'tech': '💻', 'fitness': '🏋️'
    }
    
    base_friends = 8 if info_density == 'light' else 10
    base_groups = 3 if info_density == 'light' else 4
    
    # 生成联系人 - 以同事和前同学为主
    contacts = [
        {
            'id': f'contact_{i}',
            'name': f'同事{i}' if i < 3 else f'前同学{i-2}',
            'interest_tags': [interests[0]] if interests else ['tech'],
            'relationship_type': '同事' if i < 3 else '好友',
            'baseline_interval': 7,
            'last_interaction_time': _days_ago(25 if i < 2 else 8),
            'chat_history_summary': '最近在讨论' + ('工作项目' if i < 3 else '前公司八卦'),
            'group_id': 1,
            'temperature': 0.2 if i < 2 else 0.6
        }
        for i in range(base_friends)
    ]
    
    # 工作群组
    groups = [
        {
            'name': '项目组-A',
            'recent_messages': [
                {'sender': '项目经理', 'content': '【截止】产品需求文档今天下班前提交', 'time': '14:00', 'type': 'announcement'},
                {'sender': '小王', 'content': '收到，正在整理', 'time': '14:05', 'type': 'text'},
            ]
        },
        {
            'name': '部门群',
            'recent_messages': [
                {'sender': 'HR', 'content': '下周团建投票：同意周六的扣1，周日的扣2', 'time': '10:00', 'type': 'vote'},
                {'sender': '小李', 'content': '1', 'time': '10:01', 'type': 'text'},
            ]
        },
        {
            'name': '前同学群',
            'recent_messages': [
                {'sender': '老王', 'content': '有人最近联系过小张吗？感觉好久没冒泡了', 'time': '09:00', 'type': 'text'},
            ]
        }
    ]
    
    groups = groups[:base_groups]
    
    # 痛点
    pain_points = []
    if 'missed_vote' in pain_focus:
        pain_points.append('工作群太多，团建投票总是错过')
    if 'silent_friend' in pain_focus:
        pain_points.append('前同事好久没联系，关系渐渐疏远')
    if 'work_ddl' in pain_focus:
        pain_points.append('项目DDL和工作消息太多，容易漏掉')
    if 'birthday' in pain_focus:
        pain_points.append('同事生日总是记不住，错过祝福很尴尬')
    
    # 构建图谱
    graph_nodes = [{'id': 'user', 'name': name, 'type': 'user', 'group': 0}]
    graph_links = []
    
    for c in contacts:
        graph_nodes.append({
            'id': c['id'],
            'name': c['name'],
            'type': 'contact',
            'group': c['group_id'],
            'weight': c['temperature'],
            'relationship_type': c['relationship_type']
        })
        graph_links.append({
            'source': 'user',
            'target': c['id'],
            'strength': c['temperature'],
            'temp': 'cooling' if c['temperature'] < 0.4 else 'normal'
        })
    
    return {
        'name': name,
        'grade': '工作2年',
        'major': major or '产品经理',
        'bio': '职场新人，努力在工作和社交间找平衡',
        'painPoints': pain_points,
        'interests': interests,
        'contacts': {'contacts': contacts},
        'groups': {'groups': groups},
        'graph': {'nodes': graph_nodes, 'links': graph_links}
    }


def _generate_interest_role(name, interests, pain_focus, info_density, major):
    """兴趣领域角色模板 - 好友多但松散，同好和频道好友为主"""
    interest_emoji = {
        'anime': '🎭', 'music': '🎵', 'sports': '⚽',
        'photography': '📷', 'gaming': '🎮', 'cosplay': '👘'
    }
    
    base_friends = 10 if info_density == 'normal' else 12
    base_groups = 5 if info_density == 'normal' else 6
    
    # 生成联系人 - 以同好为主
    interest_names = {
        'anime': ['动漫', '二次元', '番剧'],
        'music': ['音乐', '摇滚', '民谣'],
        'sports': ['篮球', '足球', '健身'],
        'photography': ['摄影', '人像', '风光'],
        'gaming': ['游戏', '主机', '手游'],
        'cosplay': ['cos', '漫展', '手办']
    }
    
    selected_interest = interests[0] if interests else 'anime'
    name_pool = interest_names.get(selected_interest, ['同好']) * 4
    
    contacts = [
        {
            'id': f'contact_{i}',
            'name': f'{name_pool[i % len(name_pool)]}搭子{i+1}',
            'interest_tags': [selected_interest],
            'relationship_type': '同好',
            'baseline_interval': 14,
            'last_interaction_time': _days_ago(20 + i * 3),
            'chat_history_summary': f'最近在聊{selected_interest}相关内容',
            'group_id': i % 3 + 1,
            'temperature': max(0.15, 0.5 - i * 0.03)
        }
        for i in range(base_friends)
    ]
    
    # 兴趣群组
    groups = [
        {
            'name': f'{selected_interest.capitalize()}同好群',
            'recent_messages': [
                {'sender': '群管理', 'content': '本周活动：周六下午线下聚会，有空的扣1', 'time': '10:00', 'type': 'vote'},
                {'sender': '小A', 'content': '1', 'time': '10:05', 'type': 'text'},
            ]
        },
        {
            'name': '漫展情报站',
            'recent_messages': [
                {'sender': '情报员', 'content': '最新漫展信息已更新到群文件，快去看看！', 'time': '09:00', 'type': 'announcement'},
            ]
        },
        {
            'name': '手办收藏家',
            'recent_messages': [
                {'sender': '收藏家老王', 'content': '这次的手办真的太好看了😭', 'time': '11:00', 'type': 'text'},
            ]
        },
        {
            'name': '线下活动群',
            'recent_messages': [
                {'sender': '活动策划', 'content': '本周六约球，有没有人？', 'time': '14:00', 'type': 'text'},
            ]
        },
        {
            'name': '新品首发群',
            'recent_messages': [
                {'sender': '官方号', 'content': '新品今日发售！限时优惠不容错过~', 'time': '10:00', 'type': 'announcement'},
            ]
        },
        {
            'name': '同好交流群',
            'recent_messages': [
                {'sender': '新人小李', 'content': '刚入坑，求带~', 'time': '15:00', 'type': 'text'},
            ]
        }
    ]
    
    groups = groups[:base_groups]
    
    # 痛点
    pain_points = []
    if 'new_interest' in pain_focus:
        pain_points.append('想认识更多志同道合的同好')
    if 'activity_missed' in pain_focus:
        pain_points.append('经常错过群里的活动报名')
    if 'interest_cooling' in pain_focus:
        pain_points.append('和部分同好渐渐没话题了')
    if 'channel_update' in pain_focus:
        pain_points.append('频道更新太多，看不过来')
    
    # 构建图谱
    graph_nodes = [{'id': 'user', 'name': name, 'type': 'user', 'group': 0}]
    graph_links = []
    
    for c in contacts:
        graph_nodes.append({
            'id': c['id'],
            'name': c['name'],
            'type': 'contact',
            'group': c['group_id'],
            'weight': c['temperature'],
            'relationship_type': c['relationship_type']
        })
        graph_links.append({
            'source': 'user',
            'target': c['id'],
            'strength': c['temperature'],
            'temp': 'cooling' if c['temperature'] < 0.3 else 'normal'
        })
    
    return {
        'name': name,
        'grade': '兴趣达人',
        'major': major or '自由职业',
        'bio': f'热爱{selected_interest}的社交达人，好友遍布各个圈子',
        'painPoints': pain_points,
        'interests': interests,
        'contacts': {'contacts': contacts},
        'groups': {'groups': groups},
        'graph': {'nodes': graph_nodes, 'links': graph_links}
    }


def _days_ago(days):
    """返回N天前的ISO格式时间"""
    from datetime import timedelta
    past = datetime.now() - timedelta(days=days)
    return past.isoformat()


# ============ 初始化相关 ============

@app.route('/api/initialize', methods=['POST'])
@require_password
def initialize():
    """初始化：加载角色数据，构建图谱"""
    global current_role, graph_engine, detector_manager
    
    data = request.get_json() or {}
    role = data.get('role', 'chen')
    
    try:
        current_role = role
        
        graph_engine = GraphEngine()
        graph_engine.load_data(role, DATA_PATH)
        
        detector_manager = ScenarioDetectorManager(graph_engine)
        detector_manager.load_data(role, DATA_PATH)
        
        with open(f"{DATA_PATH}/{role}/profile.json", "r", encoding="utf-8") as f:
            profile = json.load(f)
        
        alerts = detector_manager.get_prioritized_alerts()
        
        return success_response({
            "role": role,
            "profile": profile,
            "graph": graph_engine.get_graph_data(),
            "initial_alerts": alerts,
            "scenario_count": {
                "group_messages": len(detector_manager.extractor.detect()),
                "buddy_cooling": len(detector_manager.cooling_detector.detect()),
                "dormant_reactivation": len(detector_manager.reactivation_detector.detect()),
                "channel_recommendations": len(detector_manager.channel_detector.detect()),
                "birthday_reminders": len(detector_manager.birthday_detector.detect()),
                "request_response": len(detector_manager.request_detector.detect())
            }
        }, "初始化成功")
        
    except FileNotFoundError:
        return error_response(f"Role '{role}' not found", 404)
    except Exception as e:
        return error_response(f"初始化失败: {str(e)}", 500)


# ============ 角色画像相关 ============

@app.route('/api/profile/<role>', methods=['GET'])
@require_password
def get_profile(role):
    """获取角色画像信息"""
    try:
        with open(f"{DATA_PATH}/{role}/profile.json", "r", encoding="utf-8") as f:
            profile = json.load(f)
        return success_response(profile)
    except FileNotFoundError:
        return error_response(f"Role '{role}' not found", 404)


@app.route('/api/profiles', methods=['GET'])
@require_password
def list_profiles():
    """获取所有可用角色列表"""
    roles = []
    for role_dir in os.listdir(DATA_PATH):
        try:
            with open(f"{DATA_PATH}/{role_dir}/profile.json", "r", encoding="utf-8") as f:
                profile = json.load(f)
                roles.append({
                    "id": profile.get("id"),
                    "name": profile.get("name"),
                    "identity_type": profile.get("identity_type"),
                    "grade": profile.get("persona", {}).get("grade"),
                    "personality": profile.get("persona", {}).get("personality")
                })
        except:
            continue
    
    return success_response(roles)


# ============ QBuddy SSE实时扫描（对话式） ============

@app.route('/api/qbuddy/scan/<role>', methods=['GET'])
@require_password
def qbuddy_scan(role):
    """
    SSE端点：实时扫描并流式返回结果
    流程：
    1. 加载历史数据
    2. 使用 LLM 分析群消息，构建/更新图谱
    3. 运行场景检测器，生成推送卡片
    """
    
    def generate():
        try:
            # Step 1: 打招呼
            yield f"data: {json.dumps({'type': 'progress', 'step': 'init', 'message': '哈咯~让我看看你的消息~'})}\n\n"
            
            # 加载用户profile
            profile = {}
            role_name = "我"
            try:
                with open(f"{DATA_PATH}/{role}/profile.json", "r", encoding="utf-8") as f:
                    profile = json.load(f)
                    role_name = profile.get("name", "我")
            except:
                pass
            
            # Step 2: 加载数据
            yield f"data: {json.dumps({'type': 'progress', 'step': 'loading', 'message': '正在加载数据...'})}\n\n"
            
            graph_engine = GraphEngine()
            graph_engine.load_data(role, DATA_PATH)
            
            # Step 3: 使用 LLM 分析所有群消息，构建图谱
            yield f"data: {json.dumps({'type': 'progress', 'step': 'llm_analyze', 'message': '正在用 AI 分析群消息，构建关系图谱...'})}\n\n"
            
            # 收集所有群消息
            all_messages = []
            try:
                with open(f"{DATA_PATH}/{role}/groups.json", "r", encoding="utf-8") as f:
                    groups_data = json.load(f)
                    for group in groups_data.get("groups", []):
                        messages = group.get("recent_messages", [])
                        if messages:
                            all_messages.extend(messages)
            except Exception as e:
                print(f"[QBuddy] 加载群消息失败: {e}")
            
            # 使用 LLM 分析消息，构建图谱
            if all_messages:
                print(f"[QBuddy] 开始LLM分析，共{len(all_messages)}条消息...")
                llm_result = llm_service.analyze_messages_for_graph(all_messages, role_name)
                print(f"[QBuddy] LLM分析完成，结果: {llm_result}")
                
                # 应用 LLM 结果到图谱
                apply_result = graph_engine.apply_llm_result(llm_result)
                
                print(f"[QBuddy] LLM 分析完成: 添加{apply_result['nodes_added']}个节点, "
                      f"更新{apply_result['nodes_updated']}个节点, "
                      f"添加{apply_result['edges_added']}条边")
                
                # 发送 LLM 分析摘要
                if apply_result.get('summary'):
                    yield f"data: {json.dumps({'type': 'dialogue', 'text': apply_result['summary']})}\n\n"
            else:
                print("[QBuddy] 没有消息需要分析")
            
            # 更新温度
            graph_engine.update_temperatures()
            
            # 获取图谱数据
            graph_data = graph_engine.get_graph_data()
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 'graph', 'message': '关系图谱构建完成~', 'graph_data': graph_data})}\n\n"
            
            # Step 4: 运行场景检测器
            detector_manager = ScenarioDetectorManager(graph_engine)
            detector_manager.load_data(role, DATA_PATH)
            
            # 加载用户profile用于语气描述
            profile = {}
            try:
                with open(f"{DATA_PATH}/{role}/profile.json", "r", encoding="utf-8") as f:
                    profile = json.load(f)
            except:
                pass
            
            # 检测器配置列表 - 添加请求响应检测
            detectors_config = [
                ('group_extract', '正在扫描群聊消息...', 'group'),
                ('request_response', '正在检查请求回复...', 'request'),
                ('buddy_cooling', '正在检查搭子关系...', 'cooling'),
                ('reactivate', '正在寻找沉寂关系...', 'reactivate'),
                ('birthday', '正在查看生日信息...', 'birthday'),
            ]
            
            all_cards = []
            
            for det_key, progress_msg, card_type in detectors_config:
                yield f"data: {json.dumps({'type': 'progress', 'step': det_key, 'message': progress_msg})}\n\n"
                time.sleep(0.5)
                
                if det_key == 'group_extract':
                    results = detector_manager.extractor.detect()
                    for r in results:
                        try:
                            card = _format_group_card(r)
                            all_cards.append(card)
                            # 推送对话+卡片
                            dialogue = _generate_group_dialogue(r)
                            yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                            time.sleep(0.5)
                            yield f"data: {json.dumps({'type': 'card', 'data': card, 'graph_highlight': _get_highlight_for_result(graph_engine, card)})}\n\n"
                            time.sleep(0.6)
                        except Exception as e:
                            print(f"[{det_key}] 处理卡片失败: {e}")
                            continue
                        
                elif det_key == 'request_response':
                    results = detector_manager.request_detector.detect()
                    for r in results:
                        try:
                            card = _format_request_card(r)
                            all_cards.append(card)
                            # 推送对话消息
                            dialogue = r.get('dialogue', '')
                            yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                            time.sleep(0.5)
                            yield f"data: {json.dumps({'type': 'card', 'data': card, 'graph_highlight': _get_highlight_for_result(graph_engine, card)})}\n\n"
                            time.sleep(0.6)
                        except Exception as e:
                            print(f"[{det_key}] 处理卡片失败: {e}")
                            continue
                        
                elif det_key == 'buddy_cooling':
                    results = detector_manager.cooling_detector.detect()
                    for r in results:
                        try:
                            card = _format_cooling_card(r)
                            all_cards.append(card)
                            dialogue = _generate_cooling_dialogue(r)
                            yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                            time.sleep(0.5)
                            yield f"data: {json.dumps({'type': 'card', 'data': card, 'graph_highlight': _get_highlight_for_result(graph_engine, card)})}\n\n"
                            time.sleep(0.6)
                        except Exception as e:
                            print(f"[{det_key}] 处理卡片失败: {e}")
                            continue
                        
                elif det_key == 'reactivate':
                    results = detector_manager.reactivation_detector.detect()
                    for r in results:
                        try:
                            card = _format_reactivate_card(r)
                            all_cards.append(card)
                            dialogue = _generate_reactivate_dialogue(r)
                            yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                            time.sleep(0.5)
                            yield f"data: {json.dumps({'type': 'card', 'data': card, 'graph_highlight': _get_highlight_for_result(graph_engine, card)})}\n\n"
                            time.sleep(0.6)
                        except Exception as e:
                            print(f"[{det_key}] 处理卡片失败: {e}")
                            continue
                        
                elif det_key == 'birthday':
                    results = detector_manager.birthday_detector.detect()
                    for r in results:
                        try:
                            # 调用LLM生成个性化祝福（失败会重试一次）
                            contact_name = r.get('name', '好友')
                            relationship = r.get('relationship_type', '好友')
                            chat_history = r.get('chat_history_summary', '')
                            
                            blessing = None
                            for attempt in range(2):  # 最多尝试2次
                                try:
                                    blessing = llm_service.generate_blessing(
                                        contact_name=contact_name,
                                        relationship=relationship,
                                        chat_history=chat_history,
                                        birthday_type='birthday',
                                        user_tone=profile.get('persona', {}).get('tone', '')
                                    )
                                    if blessing:
                                        break
                                except Exception as e:
                                    print(f"生成祝福失败 (尝试 {attempt + 1}): {e}")
                            
                            r['personalized_blessing'] = blessing or f"生日快乐呀{contact_name}！🎂 愿你天天开心~"
                            
                            card = _format_birthday_card(r)
                            all_cards.append(card)
                            dialogue = _generate_birthday_dialogue(r)
                            yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                            time.sleep(0.5)
                            yield f"data: {json.dumps({'type': 'card', 'data': card, 'graph_highlight': _get_highlight_for_result(graph_engine, card)})}\n\n"
                            time.sleep(0.6)
                        except Exception as e:
                            print(f"[{det_key}] 处理卡片失败: {e}")
                            continue
            
            # Step 2.5: 好友动态检测 (buddy_activity)
            yield f"data: {json.dumps({'type': 'progress', 'step': 'buddy_activity', 'message': '正在查看好友动态...'})}\n\n"
            time.sleep(0.5)
            
            try:
                dynamics_path = f"{DATA_PATH}/{role}/dynamics.json"
                with open(dynamics_path, "r", encoding="utf-8") as f:
                    dynamics_data = json.load(f)
                
                # 获取用户兴趣和联系人
                user_interests = profile.get('persona', {}).get('interests', [])
                contact_names = set(c.get('name', '') for c in contacts_data[:20]) if contacts_data else set()
                
                buddy_activity_count = 0
                for dyn in dynamics_data.get('dynamics', []):
                    related_interests = dyn.get('related_interests', [])
                    author = dyn.get('author', '')
                    
                    # 判断是否相关：兴趣交集 或 作者是联系人
                    is_interest_relevant = bool(set(related_interests) & set(user_interests))
                    is_contact_relevant = author in contact_names
                    
                    # 只推送相关动态（最多3条）
                    if is_interest_relevant or is_contact_relevant:
                        card = _format_buddy_activity_card(dyn, is_interest_relevant)
                        all_cards.append(card)
                        if is_interest_relevant:
                            dialogue = f"发现同好动态！{author}的动态和你的兴趣相关 ✨"
                        else:
                            dialogue = f"你的好友{author}发布了新动态"
                        dialogues.append(dialogue)
                        yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                        time.sleep(0.5)
                        yield f"data: {json.dumps({'type': 'card', 'data': card, 'graph_highlight': {}})}\n\n"
                        time.sleep(0.6)
                        buddy_activity_count += 1
                        if buddy_activity_count >= 3:
                            break
            except Exception as e:
                print(f"加载好友动态失败: {e}")
            
            # Step 2.6: QQ生态同好检测 (ecosystem)
            yield f"data: {json.dumps({'type': 'progress', 'step': 'ecosystem', 'message': '正在分析QQ生态同好...'})}\n\n"
            time.sleep(0.5)
            
            try:
                ecosystem_path = f"{DATA_PATH}/{role}/ecosystem.json"
                with open(ecosystem_path, "r", encoding="utf-8") as f:
                    ecosystem_data = json.load(f)
                
                # 读取contacts用于查找共同爱好的好友
                contacts_list = []
                try:
                    with open(f"{DATA_PATH}/{role}/contacts.json", "r", encoding="utf-8") as cf:
                        contacts_data = json.load(cf)
                        contacts_list = contacts_data.get('contacts', [])
                except:
                    pass
                card = _format_ecosystem_card(ecosystem_data, profile.get('persona', {}).get('interests', []), contacts_list)
                all_cards.append(card)
                
                dialogue = "发现你和朋友们在QQ音乐、QQ阅读等有共同爱好哦~"
                yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                time.sleep(0.5)
                yield f"data: {json.dumps({'type': 'card', 'data': card, 'graph_highlight': {}})}\n\n"
                time.sleep(0.6)
            except Exception as e:
                print(f"加载生态数据失败: {e}")
            
            # Step 2.7: 频道推荐检测 (channel)
            yield f"data: {json.dumps({'type': 'progress', 'step': 'channel', 'message': '正在推荐兴趣频道...'})}\n\n"
            time.sleep(0.5)
            
            user_interests = profile.get('persona', {}).get('interests', [])
            if user_interests:
                channel_cards = _generate_channel_recommendations(user_interests, role)
                for channel_card in channel_cards:
                    all_cards.append(channel_card)
                    dialogue = f"根据你的「{channel_card.get('detail', {}).get('matchInterest', '兴趣')}」爱好，推荐你加入 {channel_card.get('title', '')}"
                    yield f"data: {json.dumps({'type': 'dialogue', 'text': dialogue})}\n\n"
                    time.sleep(0.5)
                    yield f"data: {json.dumps({'type': 'card', 'data': channel_card, 'graph_highlight': {}})}\n\n"
                    time.sleep(0.6)
            
            # Step 3: 完成总结
            card_end = time.time()
            card_time = card_end - graph_end
            
            if all_cards:
                summary = f"好啦~帮你整理完了，一共{len(all_cards)}件需要关注的事，快来看看吧~"
            else:
                summary = "看起来一切都很顺利呢！没有需要特别提醒的事项~"
            
            yield f"data: {json.dumps({'type': 'dialogue', 'text': summary})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'total': len(all_cards), 'performance': {'graph_build_time': round(graph_time, 2), 'card_gen_time': round(card_time, 2), 'total_time': round(graph_time + card_time, 2)}})}\n\n"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': f'扫描出错: {str(e)}'})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


# ============ QBuddy 聊天API ============

@app.route('/api/qbuddy/chat', methods=['POST'])
@require_password
def qbuddy_chat():
    """
    处理用户发送的聊天消息，返回QBuddy的回复
    """
    data = request.get_json() or {}
    message = data.get('message', '')
    role = data.get('role', 'chen')
    
    if not message:
        return error_response("消息不能为空", 400)
    
    try:
        # 读取用户profile获取语气信息
        user_profile = {}
        user_tone = ''
        user_name = '用户'
        try:
            with open(f"{DATA_PATH}/{role}/profile.json", "r", encoding="utf-8") as f:
                user_profile = json.load(f)
                user_tone = user_profile.get('persona', {}).get('tone', '')
                user_name = user_profile.get('name', '用户')
        except Exception as e:
            print(f"读取profile失败: {e}")
        
        # 预设回复模板
        preset_replies = {
            '好的': ['收到~有需要随时叫我哦~', '好嘞！有事再找我~', '没问题！'],
            '知道了': ['明白~', '好的呀！', '收到！'],
            '谢谢': ['不客气~', '有需要再找我~', '客气啥呀'],
            '再见': ['拜拜~有需要叫我~', '下次见！'],
            '看看': ['让我帮你看看~'],
            '还有什么': ['让我想想...好像都提醒你了，可以点击卡片详情查看哦~'],
            '没了': ['好嘞！那我先休息啦~有事再叫我~'],
        }
        
        # 检查是否匹配预设回复
        for key, replies in preset_replies.items():
            if key in message:
                return success_response({
                    'reply': random.choice(replies)
                })
        
        # 使用DeepSeek生成回复 - 加入用户语气描述
        tone_instruction = f"用户「{user_name}」的说话风格是：{user_tone}" if user_tone else ""
        
        system_prompt = f"""你是QBuddy，一个贴心的QQ智能助手。你的特点是：
1. 温暖、亲切、像朋友一样聊天
2. 回复简洁，不超过50字
3. 偶尔用emoji
4. 主动关心用户

{tone_instruction}

当前场景：用户刚刚收到了你推送的一些提醒（DDL、搭子关系、生日、好友动态、频道推荐等），正在和你聊天。"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        
        reply = llm_service._call_llm(messages, temperature=0.8)
        
        if not reply:
            # Fallback回复
            replies = [
                "嗯嗯，我听到了~还有什么需要帮忙的吗？",
                "好的呀！有需要随时说~",
                "我在呢，有什么事？",
                "明白~还有什么想了解的？"
            ]
            reply = random.choice(replies)
        
        return success_response({
            'reply': reply.strip()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(f"生成回复失败: {str(e)}", 500)


# ============ 卡片格式化函数 ============

def _generate_group_dialogue(r):
    """生成群消息对话文本"""
    msg_type = r.get('type', 'announcement')
    group = r.get('source_group', '群聊')
    
    if msg_type == 'announcement':
        return f"📢 {group}有新公告，快看看！"
    elif msg_type == 'vote':
        return f"🗳️ {group}有个投票等你参与~"
    elif msg_type == 'at_reminder':
        return f"@你 了！{group}有人找你~"
    else:
        return f"💬 {group}有消息需要你关注"

def _generate_cooling_dialogue(r):
    """生成搭子降温对话文本"""
    name = r.get('name', 'TA')
    hours = r.get('hours_since', 0)
    days = int(hours / 24)
    if days > 0:
        return f"感觉和{name}好久没聊了...都快{days}天了"
    else:
        return f"你跟{name}好像有点久没互动了？"

def _generate_reactivate_dialogue(r):
    """生成沉寂激活对话文本"""
    name = r.get('name', 'TA')
    signal = r.get('event_signal', '')
    if '考研' in signal:
        return f"听说{name}考研出分了！要不要去聊聊？"
    elif '生日' in signal:
        return f"{name}快过生日了，可以趁机重新联系~"
    else:
        return f"好像可以跟{name}重新联系一下了？"

def _generate_birthday_dialogue(r):
    """生成生日提醒对话文本"""
    name = r.get('name', '好友')
    days = r.get('days_until', 0)
    if days == 0:
        return f"🎂 今天是{name}的生日！记得送祝福哦~"
    elif days == 1:
        return f"🎂 明天就是{name}的生日了！准备好了吗？"
    else:
        return f"🎂 {name}的生日还有{days}天，提前准备一下？"


def _get_highlight_for_result(graph_engine, card):
    """根据卡片信息生成图谱高亮数据"""
    contact_name = card.get('contact_name', '')
    highlight_nodes = []
    highlight_edges = []
    
    if not contact_name:
        return {'nodes': [], 'edges': []}
    
    # 在图谱中查找对应联系人节点
    for cid, contact in graph_engine.contacts.items():
        # 模糊匹配：去除emoji后比较
        clean_name = contact_name.replace(' ', '').strip()
        clean_cname = contact.name.replace(' ', '').strip()
        if clean_name in clean_cname or clean_cname in clean_name:
            highlight_nodes.append(cid)
            edge_key = f"user->{cid}"
            if edge_key in graph_engine.edges:
                highlight_edges.append(edge_key)
            break
    
    return {'nodes': highlight_nodes, 'edges': highlight_edges}


def _format_group_card(r):
    """格式化群消息卡片"""
    msg_type = r.get('type', 'announcement')
    type_config = {
        'announcement': {'icon': '📢', 'title': '公告提醒'},
        'vote': {'icon': '🗳️', 'title': '投票提醒'},
        'at_reminder': {'icon': '@', 'title': '@提醒'}
    }
    config = type_config.get(msg_type, type_config['announcement'])
    
    return {
        'type': msg_type if msg_type != 'at_reminder' else 'at',
        'category': 'todo',
        'categoryLabel': '📋 待办提醒',
        'title': f"{config['icon']} {config['title']}",
        'summary': r.get('content', '')[:50] + '...' if len(r.get('content', '')) > 50 else r.get('content', ''),
        'detail': {
            'group': r.get('source_group', '未知群'),
            'content': r.get('content', ''),
            'deadline': r.get('deadline'),
            'options': r.get('options'),
            'sender': r.get('sender', '')
        },
        'contact_name': r.get('sender', ''),
        'actions': ['jump', 'not_interested'],
        'urgency': r.get('urgency', 'medium')
    }


def _format_cooling_card(r):
    """格式化搭子降温卡片"""
    return {
        'type': 'buddy_cooling',
        'category': 'social',
        'categoryLabel': '💬 社交温度',
        'title': f"🔥 搭子降温提醒",
        'summary': f"你和小{r.get('name', 'TA')}已经很久没互动了",
        'detail': {
            'contact': r.get('name', 'TA'),
            'relationship': r.get('relationship_type', '搭子'),
            'baselineInfo': f"基线频率：每{int(r.get('baseline_interval', 0))}小时",
            'lastInteraction': f"最近互动：{r.get('hours_since', 0)}小时前",
            'coolingRatio': r.get('cooling_ratio', 0),
            'temperature': r.get('temperature', 0),
            'suggestedMessage': f"嘿~最近忙啥呢？好久没一起{r.get('tags', ['玩'])[0] if r.get('tags') else '玩'}了"
        },
        'contact_name': r.get('name', ''),
        'actions': ['send_greeting', 'not_interested'],
        'urgency': r.get('urgency', 'medium')
    }


def _format_reactivate_card(r):
    """格式化沉寂激活卡片"""
    greeting = r.get('greeting_suggestion', '好久不见，最近怎么样？')
    return {
        'type': 'reactivate',
        'category': 'social',
        'categoryLabel': '💬 社交温度',
        'title': f"💤 沉寂关系激活",
        'summary': f"你和小{r.get('name', 'TA')}可以重新联系了",
        'detail': {
            'contact': r.get('name', 'TA'),
            'relationship': r.get('relationship_type', '好友'),
            'trigger': r.get('event_signal', '好久没联系了'),
            'topicContext': r.get('chat_history_summary', ''),
            'suggestedGreeting': greeting
        },
        'contact_name': r.get('name', ''),
        'actions': ['send_greeting', 'not_interested'],
        'urgency': r.get('urgency', 'medium')
    }


def _format_birthday_card(r):
    """格式化生日提醒卡片"""
    days_text = "今天" if r.get('is_today') else f"{r.get('days_until', 0)}天后"
    blessing = r.get('personalized_blessing', '生日快乐！')
    return {
        'type': 'birthday',
        'category': 'birthday',
        'categoryLabel': '🎂 特别日子',
        'title': f"🎂 生日提醒 - {r.get('name', '好友')}",
        'summary': f"{r.get('name', '好友')}的生日是{days_text}",
        'detail': {
            'contact': r.get('name', 'TA'),
            'relationship': r.get('relationship_type', '好友'),
            'birthday': r.get('birthday', ''),
            'daysUntil': r.get('days_until', 0),
            'isToday': r.get('is_today', False),
            'blessing': blessing
        },
        'contact_name': r.get('name', ''),
        'actions': ['send_blessing', 'not_interested'],
        'urgency': r.get('urgency', 'medium')
    }


def _format_request_card(r):
    """格式化请求响应卡片"""
    scenario = r.get('scenario', '')
    card_type = 'accepted_request' if scenario == 'accepted_request' else 'unreplied_request'
    
    if card_type == 'accepted_request':
        title = "📋 答应过的请求"
        summary = f"{r.get('sender', 'TA')}让你帮忙，别忘了哦~"
        actions = ['mark_done', 'not_interested']
    else:
        title = "📬 待回复的请求"
        summary = f"{r.get('sender', 'TA')}在等你回复呢~"
        actions = ['reply', 'not_interested']
    
    return {
        'type': card_type,
        'category': 'todo',
        'categoryLabel': '📋 待办提醒',
        'title': title,
        'summary': summary,
        'detail': {
            'sender': r.get('sender', 'TA'),
            'content': r.get('content', ''),
            'group': r.get('source_group', '群聊'),
            'time': r.get('time', ''),
            'action_required': r.get('action_required', '')
        },
        'contact_name': r.get('sender', ''),
        'actions': actions,
        'urgency': r.get('urgency', 'medium')
    }


def _format_buddy_activity_card(dyn, is_relevant=False):
    """格式化好友动态卡片"""
    relevance_tag = "✨ 同好相关" if is_relevant else ""
    return {
        'type': 'buddy_activity',
        'category': 'buddy_activity',
        'categoryLabel': f'🎵 同好动态 {relevance_tag}'.strip(),
        'title': f"📱 好友动态 - {dyn.get('author', '好友')}",
        'summary': dyn.get('content', '')[:50] + '...' if len(dyn.get('content', '')) > 50 else dyn.get('content', ''),
        'detail': {
            'author': dyn.get('author', '好友'),
            'avatar': dyn.get('avatar', '👤'),
            'content': dyn.get('content', ''),
            'images': dyn.get('images', []),
            'time': dyn.get('time', ''),
            'likes': dyn.get('likes', 0),
            'comments': dyn.get('comments', 0),
            'related_interests': dyn.get('related_interests', []),
            'isRelevant': is_relevant
        },
        'contact_name': dyn.get('author', ''),
        'actions': ['view_dynamic', 'not_interested'],
        'urgency': 'high' if is_relevant else 'low'
    }


def _format_ecosystem_card(ecosystem_data, user_interests=None, contacts=None):
    """格式化生态系统匹配卡片"""
    song = ecosystem_data.get('qq_music', {}).get('recently_listened', ['未知歌曲'])[0]
    book = ecosystem_data.get('qq_reading', {}).get('recently_reading', ['未知书籍'])[0]
    video = ecosystem_data.get('tencent_video', {}).get('recently_watching', ['未知视频'])[0]
    
    # 计算共同兴趣匹配度
    match_count = 0
    if user_interests:
        for interest in user_interests:
            if interest in str(ecosystem_data):
                match_count += 1
        match_label = f"✨ {match_count}个共同爱好" if match_count > 0 else ""
    else:
        match_label = ""
    
    # 从contacts中提取有共同爱好的好友（mutualConnections）
    mutual_connections = []
    if contacts:
        interest_keywords = set()
        if user_interests:
            interest_keywords = set(user_interests)
        # 也从ecosystem数据中提取关键词
        for item in ecosystem_data.get('qq_music', {}).get('recently_listened', []):
            interest_keywords.add(item.split(' - ')[-1] if ' - ' in item else item)
        for item in ecosystem_data.get('tencent_video', {}).get('recently_watching', []):
            interest_keywords.add(item)
        
        for c in contacts:
            c_tags = set(c.get('interest_tags', []) + c.get('tags', []))
            if c_tags & interest_keywords:
                mutual_connections.append({'name': c.get('name', '好友'), 'shared': list(c_tags & interest_keywords)[:3]})
    
    # 取第一个匹配好友作为contact_name（供前端跳转用）
    primary_contact = mutual_connections[0]['name'] if mutual_connections else ''
    
    return {
        'type': 'ecosystem',
        'category': 'buddy_activity',
        'categoryLabel': f'🎵 同好动态 {match_label}'.strip(),
        'title': "🎧 QQ生态同好",
        'summary': f"和朋友们在音乐、阅读、视频上都有共同品味~" if match_count > 0 else f"发现你和朋友们的QQ生态偏好~",
        'detail': {
            'qq_music': ecosystem_data.get('qq_music', {}),
            'qq_reading': ecosystem_data.get('qq_reading', {}),
            'tencent_video': ecosystem_data.get('tencent_video', {}),
            'recommendations': {
                'song': song,
                'book': book,
                'video': video
            },
            'matchCount': match_count,
            'matchInterests': user_interests[:3] if user_interests else [],
            'mutualConnections': mutual_connections
        },
        'contact_name': primary_contact,
        'actions': ['view_music', 'view_reading', 'view_video'],
        'urgency': 'medium'
    }


def _generate_channel_recommendations(user_interests, role):
    """基于用户兴趣生成频道推荐卡片"""
    # 频道推荐池
    channel_pool = {
        '编程': [
            {'name': '程序员技术交流', 'memberCount': 85000, 'tags': ['编程', '技术', '代码']},
            {'name': 'Python爱好者社区', 'memberCount': 62000, 'tags': ['Python', '编程', '开发']},
            {'name': '算法与数据结构', 'memberCount': 45000, 'tags': ['算法', '刷题', 'LeetCode']}
        ],
        '算法': [
            {'name': 'LeetCode刷题打卡', 'memberCount': 52000, 'tags': ['算法', '刷题', '面试']},
            {'name': 'ACM竞赛交流', 'memberCount': 38000, 'tags': ['竞赛', '算法', '编程']}
        ],
        '游戏': [
            {'name': '王者荣耀开黑群', 'memberCount': 120000, 'tags': ['游戏', '开黑', '王者荣耀']},
            {'name': '原神玩家社区', 'memberCount': 95000, 'tags': ['游戏', '原神', '二次元']},
            {'name': 'Steam游戏折扣', 'memberCount': 78000, 'tags': ['游戏', 'Steam', '折扣']}
        ],
        '考研': [
            {'name': '考研资料分享', 'memberCount': 110000, 'tags': ['考研', '资料', '学习']},
            {'name': '24考研交流群', 'memberCount': 68000, 'tags': ['考研', '交流', '经验']}
        ],
        '篮球': [
            {'name': '篮球爱好者联盟', 'memberCount': 88000, 'tags': ['篮球', '运动', '约球']},
            {'name': 'NBA球迷社区', 'memberCount': 150000, 'tags': ['NBA', '篮球', '赛事']}
        ],
        '音乐': [
            {'name': 'QQ音乐粉丝群', 'memberCount': 65000, 'tags': ['音乐', 'QQ音乐', '粉丝']},
            {'name': '独立音乐人社区', 'memberCount': 42000, 'tags': ['音乐', '创作', '独立']}
        ],
        '阅读': [
            {'name': '读书分享会', 'memberCount': 55000, 'tags': ['读书', '阅读', '分享']},
            {'name': '技术书籍交流', 'memberCount': 35000, 'tags': ['技术', '书籍', '学习']}
        ],
        '二次元': [
            {'name': '动漫交流社区', 'memberCount': 130000, 'tags': ['动漫', '二次元', '番剧']},
            {'name': '手办收藏家', 'memberCount': 48000, 'tags': ['手办', '收藏', '二次元']}
        ],
        # ===== 产品经理专属频道（小林） =====
        '咖啡探店': [
            {'name': '咖啡探店小分队', 'memberCount': 15000, 'tags': ['咖啡', '探店', '生活']},
            {'name': '互联网PM交流群', 'memberCount': 85000, 'tags': ['产品经理', '互联网', '职场']}
        ],
        '播客': [
            {'name': '产品经理播客群', 'memberCount': 32000, 'tags': ['播客', '产品经理', '知识']},
            {'name': '深度阅读分享', 'memberCount': 28000, 'tags': ['播客', '阅读', '独立']}
        ],
        '用户体验': [
            {'name': '用户体验设计交流', 'memberCount': 45000, 'tags': ['UX', '用户体验', '设计']},
            {'name': '用户研究方法论', 'memberCount': 22000, 'tags': ['用户调研', '产品', '方法']}
        ],
        '追剧': [
            {'name': '追剧交流群', 'memberCount': 92000, 'tags': ['追剧', '影视', '综艺']},
            {'name': '影视解说社区', 'memberCount': 38000, 'tags': ['影视', '解说', '观后感']}
        ],
        '城市骑行': [
            {'name': '城市骑行俱乐部', 'memberCount': 28000, 'tags': ['骑行', '运动', '城市']},
            {'name': '户外运动交友', 'memberCount': 45000, 'tags': ['户外', '运动', '旅行']}
        ],
        # ===== 插画师专属频道（小周） =====
        '插画': [
            {'name': '插画师互助群', 'memberCount': 230000, 'tags': ['插画', '绘画', '创作']},
            {'name': '商业插画交流', 'memberCount': 68000, 'tags': ['商业插画', '约稿', '合作']}
        ],
        '摄影': [
            {'name': '胶片摄影群', 'memberCount': 89000, 'tags': ['胶片', '摄影', '暗房']},
            {'name': '人像摄影交流', 'memberCount': 120000, 'tags': ['人像', '摄影', '约拍']}
        ],
        '手账': [
            {'name': '文具手账群', 'memberCount': 180000, 'tags': ['手账', '文具', '文具控']},
            {'name': '手账素材分享', 'memberCount': 42000, 'tags': ['手账', '素材', 'MT胶带']}
        ],
        '独立音乐': [
            {'name': '独立音乐人社区', 'memberCount': 52000, 'tags': ['独立音乐', '民谣', '创作']},
            {'name': '音乐创作交流', 'memberCount': 35000, 'tags': ['音乐', '创作', '乐器']}
        ],
        '胶片相机': [
            {'name': '胶片摄影群', 'memberCount': 89000, 'tags': ['胶片', '相机', '暗房']},
            {'name': '胶片冲扫推荐', 'memberCount': 18000, 'tags': ['冲扫', '胶片', 'portra400']}
        ]
    }
    
    # 频道名到前端频道ID的映射（用于前端跳转）
    channel_name_to_id = {
        # 通用
        'CS保研交流圈': 'ch_001',
        '王者荣耀开黑群': 'ch_002',
        '图书馆预约助手': 'ch_003',
        '算法刷题打卡': 'ch_004',
        '二次元同好会': 'ch_001',
        '校园美食地图': 'ch_002',
        '羽毛球约球群': 'ch_003',
        '学生会活动发布': 'ch_004',
        '吉他入门指南': 'ch_001',
        '新生互助联盟': 'ch_002',
        '漫展情报站': 'ch_003',
        '电赛交流区': 'ch_004',
        # 小林专属（产品经理）- 统一使用ch_001-ch_004
        '咖啡探店小分队': 'ch_001',
        '互联网PM交流群': 'ch_002',
        '产品经理播客群': 'ch_003',
        '深度阅读分享': 'ch_004',
        '用户体验设计交流': 'ch_001',
        '用户研究方法论': 'ch_002',
        '追剧交流群': 'ch_003',
        '影视解说社区': 'ch_004',
        '城市骑行俱乐部': 'ch_001',
        '户外运动交友': 'ch_002',
        # 小周专属（插画师）- 统一使用ch_001-ch_004
        '插画师互助群': 'ch_001',
        '商业插画交流': 'ch_002',
        '胶片摄影群': 'ch_003',
        '人像摄影交流': 'ch_004',
        '文具手账群': 'ch_001',
        '手账素材分享': 'ch_002',
        '独立音乐人社区': 'ch_003',
        '音乐创作交流': 'ch_004',
        '胶片冲扫推荐': 'ch_001',
    }
    
    # 兴趣中英文映射
    interest_map = {
        '编程': '编程', '程序': '编程', '代码': '编程',
        '算法': '算法', '刷题': '算法', 'LeetCode': '算法',
        '游戏': '游戏', '开黑': '游戏', '王者荣耀': '游戏',
        '考研': '考研', '保研': '考研',
        '篮球': '篮球', '运动': '篮球',
        '音乐': '音乐', '听歌': '音乐',
        '阅读': '阅读', '读书': '阅读', '书籍': '阅读',
        '动漫': '二次元', '动画': '二次元', '番剧': '二次元',
        # 产品经理兴趣（小林）
        '咖啡探店': '咖啡探店', '咖啡': '咖啡探店', '探店': '咖啡探店',
        '播客': '播客',
        '用户体验': '用户体验', 'UX': '用户体验', '用户调研': '用户体验',
        '追剧': '追剧', '影视': '追剧',
        '城市骑行': '城市骑行', '骑行': '城市骑行',
        # 插画师兴趣（小周）
        '插画': '插画', '绘画': '插画', '商稿': '插画',
        '摄影': '摄影', '拍照': '摄影',
        '胶片相机': '胶片相机', '胶片': '胶片相机', '冲扫': '胶片相机',
        '手账': '手账', '文具': '手账',
        '独立音乐': '独立音乐', '民谣': '独立音乐',
    }
    
    recommendations = []
    shown_channels = set()
    
    for interest in user_interests:
        matched_key = interest_map.get(interest, interest)
        channels = channel_pool.get(matched_key, [])
        
        for channel in channels[:1]:  # 每个兴趣最多1个推荐
            if channel['name'] not in shown_channels:
                shown_channels.add(channel['name'])
                # 获取前端频道ID，默认为从频道名生成的ID
                frontend_channel_id = channel_name_to_id.get(channel['name'], ''.join(c for c in channel['name'] if c.isalnum())[:20])
                card = _format_channel_card(channel, interest, frontend_channel_id)
                recommendations.append(card)
        
        if len(recommendations) >= 3:  # 最多3个推荐
            break
    
    return recommendations

def _format_channel_card(channel_info, match_interest, frontend_channel_id=None):
    """格式化频道推荐卡片"""
    channel_name = channel_info.get('name', '推荐频道')
    member_count = channel_info.get('memberCount', 0)
    
    # 使用传入的前端频道ID，如果没有则从频道名生成
    channel_id = frontend_channel_id or ''.join(c for c in channel_name if c.isalnum())[:20]
    
    return {
        'type': 'channel',
        'category': 'channel',
        'categoryLabel': '🔍 频道推荐',
        'title': f"📢 {channel_name}",
        'summary': f"成员 {member_count:,} 人 · 基于「{match_interest}」推荐",
        'detail': {
            'channelName': channel_name,
            'channelId': channel_id,
            'memberCount': member_count,
            'matchInterest': match_interest,
            'tags': channel_info.get('tags', []),
            'reason': f"你和好友都在关注「{match_interest}」相关内容",
            'jumpUrl': f"https://qun.qq.com/post/detail?channelId={channel_id}"
        },
        'contact_name': '',
        'actions': ['join_channel', 'not_interested'],
        'urgency': 'low'
    }


# ============ QBuddy 新版 API（整合所有8个步骤） ============

# 导入新的服务模块
try:
    from qb_service import QBuddyService, get_or_create_service, stop_all_services
    QB_SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"[Warning] qb_service 模块导入失败: {e}")
    QB_SERVICE_AVAILABLE = False


@app.route('/api/qbuddy/init', methods=['POST'])
@require_password
def qbuddy_init():
    """
    步骤整合：初始化 QBuddy 服务
    执行步骤1-3：构建图谱、提取skill、分析动态
    """
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    data = request.get_json() or {}
    role = data.get('role', 'chen')
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        result = service.initialize()
        
        return success_response({
            "role": role,
            "graph_data": result["step1_graph"]["graph_data"],
            "skill_md": result["step2_skill"],
            "relevant_content": result["step3_dynamics"],
            "message": "QBuddy 初始化完成"
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(f"初始化失败: {str(e)}", 500)


@app.route('/api/qbuddy/skill', methods=['GET'])
@require_password
def get_user_skill():
    """
    获取用户的 skill.md
    """
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    role = request.args.get('role', 'chen')
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        
        if not service.user_skill_md:
            service.initialize()
        
        return success_response({
            "skill_md": service.user_skill_md or "# 默认风格\n普通聊天风格"
        })
    
    except Exception as e:
        return error_response(f"获取skill失败: {str(e)}", 500)


@app.route('/api/qbuddy/background/start', methods=['POST'])
@require_password
def start_background_services():
    """
    启动后台服务（步骤4：消息监听、步骤5：温度监控）
    """
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    data = request.get_json() or {}
    role = data.get('role', 'chen')
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        
        # 定义回调函数
        def on_alert(alert):
            print(f"[Alert] 触发告警: {alert.get('rule_name')}")
        
        service.start_background_services(on_alert=on_alert)
        
        return success_response({
            "message": "后台服务已启动",
            "services": {
                "message_listener": service.message_listener is not None,
                "temperature_monitor": service.temp_monitor is not None
            }
        })
    
    except Exception as e:
        return error_response(f"启动后台服务失败: {str(e)}", 500)


@app.route('/api/qbuddy/background/stop', methods=['POST'])
@require_password
def stop_background_services():
    """停止后台服务"""
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    try:
        stop_all_services()
        return success_response({"message": "后台服务已停止"})
    except Exception as e:
        return error_response(f"停止后台服务失败: {str(e)}", 500)


@app.route('/api/qbuddy/alerts', methods=['GET'])
@require_password
def get_pending_alerts():
    """
    获取待处理的告警（用于前端闪亮提醒）
    """
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    role = request.args.get('role', 'chen')
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        
        alerts = []
        if service.temp_monitor:
            alerts = service.temp_monitor.get_pending_alerts()
        
        return success_response({
            "alerts": alerts,
            "has_new_alerts": len(alerts) > 0
        })
    
    except Exception as e:
        return error_response(f"获取告警失败: {str(e)}", 500)


@app.route('/api/qbuddy/push-cards', methods=['GET'])
@require_password
def get_push_cards():
    """
    获取聚合推送卡片（步骤6）
    """
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    role = request.args.get('role', 'chen')
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        cards = service.generate_push_cards()
        
        return success_response({
            "cards": cards,
            "total": len(cards)
        })
    
    except Exception as e:
        return error_response(f"生成推送卡片失败: {str(e)}", 500)


@app.route('/api/qbuddy/chat-v2', methods=['POST'])
@require_password
def qbuddy_chat_v2():
    """
    QBuddy 对话 API（步骤7：Tool Calling）
    """
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    data = request.get_json() or {}
    message = data.get('message', '')
    role = data.get('role', 'chen')
    
    if not message:
        return error_response("消息不能为空", 400)
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        result = service.chat(message)
        
        return success_response(result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(f"对话失败: {str(e)}", 500)


@app.route('/api/qbuddy/feedback', methods=['POST'])
@require_password
def record_feedback():
    """
    记录用户反馈（步骤8：动态阈值调整）
    """
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    data = request.get_json() or {}
    role = data.get('role', 'chen')
    card_type = data.get('card_type', '')
    action = data.get('action', '')
    interacted = data.get('interacted', False)
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        service.record_interaction(card_type, action, interacted)
        
        return success_response({
            "message": "反馈已记录",
            "thresholds": service.get_threshold_config()
        })
    
    except Exception as e:
        return error_response(f"记录反馈失败: {str(e)}", 500)


@app.route('/api/qbuddy/thresholds', methods=['GET'])
@require_password
def get_thresholds():
    """获取当前阈值配置"""
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    role = request.args.get('role', 'chen')
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        return success_response(service.get_threshold_config())
    except Exception as e:
        return error_response(f"获取阈值失败: {str(e)}", 500)


@app.route('/api/qbuddy/thresholds/reset', methods=['POST'])
@require_password
def reset_thresholds():
    """重置阈值到默认值"""
    if not QB_SERVICE_AVAILABLE:
        return error_response("QB服务模块不可用", 500)
    
    data = request.get_json() or {}
    role = data.get('role', 'chen')
    
    try:
        service = get_or_create_service(role, DATA_PATH)
        service.threshold_optimizer.reset_thresholds()
        return success_response({"message": "阈值已重置"})
    except Exception as e:
        return error_response(f"重置阈值失败: {str(e)}", 500)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    print("=" * 50)
    print("QBuddy Backend Starting...")
    print(f"Access Password: {ACCESS_PASSWORD}")
    print(f"Data Path: {DATA_PATH}")
    print(f"Port: {port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

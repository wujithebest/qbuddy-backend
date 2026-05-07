"""
QBuddy后端测试脚本
"""
import requests
import json

BASE_URL = "http://localhost:5000/api"
PASSWORD = "qbuddy2026"

headers = {
    "X-Access-Password": PASSWORD,
    "Content-Type": "application/json"
}

def test_health():
    """健康检查"""
    print("\n=== 测试健康检查 ===")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"状态码: {resp.status_code}")
    print(f"响应: {json.dumps(resp.json(), ensure_ascii=False, indent=2)}")
    return resp.status_code == 200

def test_list_profiles():
    """获取角色列表"""
    print("\n=== 测试获取角色列表 ===")
    resp = requests.get(f"{BASE_URL}/profiles", headers=headers)
    print(f"状态码: {resp.status_code}")
    data = resp.json()
    print(f"可用角色: {json.dumps(data.get('data', []), ensure_ascii=False, indent=2)}")
    return data.get('code') == 200

def test_initialize(role='lin'):
    """初始化"""
    print(f"\n=== 测试初始化 (角色: {role}) ===")
    resp = requests.post(f"{BASE_URL}/initialize", headers=headers, json={"role": role})
    print(f"状态码: {resp.status_code}")
    data = resp.json()
    if data.get('code') == 200:
        print(f"初始化成功!")
        print(f"场景统计: {json.dumps(data['data'].get('scenario_count', {}), ensure_ascii=False)}")
        print(f"初始提醒数量: {len(data['data'].get('initial_alerts', []))}")
    else:
        print(f"错误: {data.get('message')}")
    return data.get('code') == 200

def test_trigger():
    """触发检测"""
    print("\n=== 测试QBuddy触发检测 ===")
    resp = requests.post(f"{BASE_URL}/qbuddy/trigger", headers=headers)
    print(f"状态码: {resp.status_code}")
    data = resp.json()
    if data.get('code') == 200:
        results = data['data']
        print(f"总提醒数: {results.get('total_alerts')}")
        
        # 打印各类场景
        all_results = results.get('all_results', {})
        for scenario, items in all_results.items():
            print(f"  {scenario}: {len(items)}条")
        
        # 打印优先级最高的3条
        print("\n优先级提醒(Top 3):")
        for i, alert in enumerate(results.get('prioritized_alerts', [])[:3], 1):
            print(f"  {i}. [{alert.get('category')}] {alert.get('name', alert.get('content', '')[:30])} - 优先级:{alert.get('priority')}")
    return data.get('code') == 200

def test_action():
    """用户操作"""
    print("\n=== 测试用户操作 ===")
    
    # 一键祝福
    print("\n1. 一键祝福:")
    resp = requests.post(f"{BASE_URL}/qbuddy/action", headers=headers, json={
        "action_type": "send_blessing",
        "contact_id": "xiaomei"
    })
    if resp.json().get('code') == 200:
        print(f"   祝福文案: {resp.json()['data'].get('blessing')}")
    
    # 重新激活
    print("\n2. 重新激活:")
    resp = requests.post(f"{BASE_URL}/qbuddy/action", headers=headers, json={
        "action_type": "reactivate",
        "contact_id": "xiaoli"
    })
    if resp.json().get('code') == 200:
        print(f"   开场白: {resp.json()['data'].get('greeting')}")

def test_graph():
    """图谱数据"""
    print("\n=== 测试图谱数据 ===")
    resp = requests.get(f"{BASE_URL}/graph/lin", headers=headers)
    data = resp.json()
    if data.get('code') == 200:
        graph = data['data']
        print(f"节点数: {graph['stats']['total_nodes']}")
        print(f"边数: {graph['stats']['total_links']}")
        print(f"平均温度: {graph['stats']['avg_temperature']}")
        print("\n节点列表:")
        for node in graph['nodes']:
            if node['id'] != 'user':
                print(f"  - {node['name']} ({node['relationship_type']}): 温度={node['temperature']}")

def test_llm():
    """LLM调用"""
    print("\n=== 测试LLM功能 ===")
    
    # 祝福生成
    print("\n1. 祝福文案生成:")
    resp = requests.post(f"{BASE_URL}/llm/blessing", headers=headers, json={
        "contact_name": "小美",
        "relationship": "闺蜜",
        "chat_history": "我们一起追同一个组合，经常一起看演唱会"
    })
    if resp.json().get('code') == 200:
        print(f"   {resp.json()['data'].get('blessing')}")
    
    # 开场白生成
    print("\n2. 开场白生成:")
    resp = requests.post(f"{BASE_URL}/llm/greeting", headers=headers, json={
        "contact_name": "小李",
        "relationship": "搭子",
        "topic_context": "考研期间几乎断联，之前经常一起开黑",
        "event_signal": "考研出分"
    })
    if resp.json().get('code') == 200:
        print(f"   {resp.json()['data'].get('greeting')}")

def test_chat_reply():
    """测试聊天回复API（问题1修复验证）"""
    print("\n=== 测试聊天回复API ===")
    resp = requests.post(f"{BASE_URL}/chat/reply", headers=headers, json={
        "contact_name": "小王",
        "relationship": "同学",
        "message": "周末一起打游戏吗？",
        "chat_history": [
            {"role": "user", "content": "最近忙什么呢"},
            {"role": "contact", "content": "在准备期末考试"},
            {"role": "user", "content": "加油！"},
            {"role": "contact", "content": "谢谢~"},
        ]
    })
    print(f"状态码: {resp.status_code}")
    data = resp.json()
    if data.get('code') == 200:
        print(f"回复: {data['data'].get('reply')}")
        return True
    else:
        print(f"错误: {data.get('message')}")
        return False

def test_custom_role_generate():
    """测试自定义角色生成（问题2修复验证）"""
    print("\n=== 测试自定义角色生成 ===")
    
    test_cases = [
        {
            "name": "社牛大学生",
            "params": {
                "identity": "college",
                "infoDensity": "overload",
                "socialStyle": "active",
                "interests": ["gaming", "anime", "sports"],
                "painFocus": ["missed_ddl", "buddy_cooling", "missed_birthday"],
                "name": "自定义大学生",
                "major": "计算机"
            }
        },
        {
            "name": "社恐打工人",
            "params": {
                "identity": "young_worker",
                "infoDensity": "light",
                "socialStyle": "introvert",
                "interests": ["reading", "music"],
                "painFocus": ["missed_vote", "silent_friend"],
                "name": "内向打工人",
                "major": "产品经理"
            }
        },
        {
            "name": "兴趣达人",
            "params": {
                "identity": "interest_focused",
                "infoDensity": "normal",
                "socialStyle": "moderate",
                "interests": ["anime", "music"],
                "painFocus": ["missed_ddl", "new_interest"],
                "name": "插画师阿雪",
                "major": "插画"
            }
        }
    ]
    
    results = []
    for case in test_cases:
        print(f"\n--- 测试场景: {case['name']} ---")
        resp = requests.post(f"{BASE_URL}/customize/generate", 
                            headers=headers, 
                            json=case['params'])
        print(f"状态码: {resp.status_code}")
        data = resp.json()
        
        if data.get('code') == 200:
            result_data = data['data']
            print(f"  角色ID: {result_data.get('id')}")
            print(f"  角色名: {result_data.get('name')}")
            
            contacts = result_data.get('contacts', {}).get('contacts', [])
            print(f"  联系人数量: {len(contacts)}")
            
            groups = result_data.get('groups', {}).get('groups', [])
            print(f"  群数量: {len(groups)}")
            for g in groups:
                msg_count = len(g.get('recent_messages', []))
                print(f"    - {g.get('name')}: {msg_count}条消息")
            
            graph = result_data.get('graph', {})
            print(f"  图谱节点: {len(graph.get('nodes', []))}")
            
            print(f"  痛点: {result_data.get('painPoints', [])}")
            results.append(True)
        else:
            print(f"  错误: {data.get('message')}")
            results.append(False)
    
    return all(results)

def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("QBuddy后端测试开始")
    print("=" * 50)
    
    tests = [
        ("健康检查", test_health),
        ("角色列表", test_list_profiles),
        ("初始化", lambda: test_initialize('lin')),
        ("触发检测", test_trigger),
        ("用户操作", test_action),
        ("图谱数据", test_graph),
        ("LLM功能", test_llm),
        ("聊天回复API", test_chat_reply),
        ("自定义角色生成", test_custom_role_generate),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"测试异常: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")
    
    passed = sum(1 for _, r in results if r)
    print(f"\n通过: {passed}/{len(results)}")

if __name__ == '__main__':
    run_all_tests()

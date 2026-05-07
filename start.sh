#!/bin/bash
# QBuddy 后端启动脚本

cd "$(dirname "$0")"

echo "检查Python依赖..."
if ! python3 -c "import flask" 2>/dev/null; then
    echo "安装依赖..."
    pip install -r requirements.txt
fi

echo "启动QBuddy后端服务..."
echo "访问密码: qbuddy2026"
echo ""

python3 app.py

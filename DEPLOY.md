# QBuddy Backend - Railway 部署指南

## 一键部署步骤

### 1. 创建 GitHub 仓库

在 GitHub 上创建一个新仓库，命名为 `qbuddy-backend`，**不要**勾选 "Add a README file"。

### 2. 推送后端代码

在终端运行以下命令（将 `YOUR_USERNAME` 替换为您的 GitHub 用户名）：

```bash
cd d:/pm_project/qbuddy_mvp/backend

# 初始化 git
git init

# 添加远程仓库
git remote add origin https://github.com/YOUR_USERNAME/qbuddy-backend.git

# 添加所有文件（.gitignore 会自动排除 .env）
git add .

# 提交
git commit -m "Initial commit"

# 推送（需要输入 GitHub 用户名和密码/Token）
git push -u origin main
```

### 3. 在 Railway 部署

1. 访问 https://railway.app/dashboard
2. 点击 "New Project" → "Deploy from GitHub repo"
3. 选择刚创建的 `qbuddy-backend` 仓库
4. Railway 会自动检测 Python 项目

### 4. 设置环境变量

在 Railway 项目设置中添加以下环境变量：

| 变量名 | 值 |
|--------|-----|
| `DEEPSEEK_API_KEY` | `sk-4a5b90817f7647d0a249de705b66e7cf` |
| `ACCESS_PASSWORD` | `qbuddy2026` |

### 5. 获取后端 URL

部署完成后，Railway 会分配一个 URL，格式类似：
`https://qbuddy-backend.up.railway.app`

### 6. 更新前端 API 地址

部署完成后告诉我后端 URL，我会帮您更新前端并重新部署。

---

## 注意事项

- **不要提交 .env 文件** - 已通过 .gitignore 排除
- **环境变量在 Railway 控制台设置** - 不在代码中
- **Railway 免费额度** - 每月 500 小时，休眠后重新激活

## 本地运行

```bash
cd backend
pip install -r requirements.txt
python app.py
```

后端将在 http://localhost:5000 运行。

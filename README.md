# Leo Ads Master v2.1 Web

亚马逊广告12维度分析系统 - Web版本

## 架构

- **前端**: 纯 HTML/CSS/JS (iOS风格)，部署到 Cloudflare Pages
- **后端**: Python FastAPI，部署到 Render / Railway / 自建服务器

## 快速开始

### 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. 前端开发

前端为纯静态页面，直接在浏览器中打开 `frontend/index.html` 即可。

生产环境部署到 Cloudflare Pages。

### 3. 部署

#### 前端 (Cloudflare Pages)

1. Fork 本仓库到 GitHub
2. 在 Cloudflare Dashboard 创建 Pages 项目
3. 绑定 GitHub 仓库，构建输出目录设为 `frontend`
4. 推送代码到 main 分支自动触发部署

#### 后端 (Render)

1. 在 [Render](https://render.com) 创建新的 Web Service
2. 连接 GitHub 仓库
3. 设置：
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
4. 部署完成后更新前端 `API_BASE` 为 Render 提供的域名

## 默认账号

- 用户名: `yangle`
- 密码: `leo0417`
- 角色: admin

## 功能特性

- 12维度广告深度分析
- 流量词架构自动分层（8层）
- 今日执行清单（加法/减法）
- 7天监控计划
- Excel报告导出
- 多用户权限管理
- LLM多厂商接入
- iOS/macOS风格UI

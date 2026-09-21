# 视频在线预览裁剪 (Video Review & Cutter)

[![CI](https://github.com/ccawmiku/video-review-cutter/actions/workflows/ci.yml/badge.svg)](https://github.com/ccawmiku/video-review-cutter/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/ccawmiku/video-review-cutter)

视频在线预览与裁剪工具是一款面向私有部署的高性能视频初筛与片段剪辑系统。本项目基于 React + TypeScript + Vite 前端与 FastAPI + Python 后端构建，结合 SQLite 持久化和 FFmpeg 处理引擎。

> **提示**：当前仓库处于 **Issue #1 基础脚手架 (Scaffold)** 阶段。本阶段确立了前后端工程骨架、UI 规范、健康检查端点、类型检查/测试配置、Docker 与 GitHub Actions CI 规范。视频扫描、流媒体播放、片段裁剪、文件移动与认证流程将在后续 Issue 中逐步实现。

---

## 技术栈与架构

- **前端 (Frontend)**:
  - React 18 + TypeScript + Vite
  - Tailwind CSS + shadcn/ui 组件规范
  - 无障碍设计 (Accessibility Landmarks / Skip Links / ARIA 规范)
  - Vitest + Testing Library + ESLint
- **后端 (Backend)**:
  - Python 3.12 + FastAPI + Uvicorn
  - Pydantic v2 设置与数据模型
  - SQLite 数据库引擎与 Session 占位
  - FFmpeg / FFprobe 服务接口抽象占位
  - Ruff 代码规范检查与格式化 + Mypy 静态类型检查 + Pytest 单元测试
- **容器与部署 (DevOps)**:
  - Docker 多阶段构建镜像
  - Docker Compose 服务编排与本地持久化/媒体卷挂载
  - GitHub Actions 持续集成自动化测试与镜像构建校验

---

## 核心存储目录规范与环境变量

本项目通过环境变量明确划分不同媒体文件的生命周期与存储路径，避免误操作源文件并确保数据安全：

| 环境变量 | 权限要求 | 默认容器路径 | 说明 |
|---|---|---|---|
| `VIDEO_ROOTS` | **只读 (RO)** | `/media/videos` | **待扫描与预览的源视频根目录**。支持配置多个目录，多个路径之间使用分号 (`;`) 或逗号 (`,`) 分割。后端扫描引擎仅做读取与分析，绝不直接修改源视频。 |
| `ARCHIVE_DIR` | **读写 (RW)** | `/media/archive` | **归档保留目录**。用于存放通过初筛审核的视频，或在线裁剪生成的高光/精彩视频片段。 |
| `DISCARDED_DIR` | **读写 (RW)** | `/media/discarded` | **废弃隔离目录**。用于隔离或标记废弃、不合格的视频。在后续文件移动实现中，不合格文件将被安全移动至此目录进行隔离，而非物理硬删除。 |
| `DATABASE_URL` | **读写 (RW)** | `sqlite:///./data/video_review.db` | **SQLite 数据库路径**。保存任务状态、元数据索引及裁剪标记。 |

### 环境变量示例 (`.env.example`)

复制 `.env.example` 为 `.env` 进行本地环境配置：

```bash
cp .env.example .env
```

```ini
# 服务基础配置
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]

# 媒体存储目录 (宿主机绝对路径或相对路径)
VIDEO_ROOTS=/media/videos;/mnt/nas/videos
ARCHIVE_DIR=/media/archive
DISCARDED_DIR=/media/discarded

# SQLite 数据库
DATABASE_URL=sqlite:///./data/video_review.db

# FFmpeg 可执行文件路径
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe

# 前端连接后端 API 地址
VITE_API_BASE_URL=http://localhost:8000
```

---

## Docker Compose 卷挂载说明

在 `docker-compose.yml` 中，视频与数据目录的挂载模式如下：

```yaml
volumes:
  - ./data:/app/data                                            # 数据库及缓存本地持久化
  - ${HOST_VIDEO_ROOT:-./mock_media/videos}:/media/videos:ro     # 源视频只读安全挂载 (:ro)
  - ${HOST_ARCHIVE_DIR:-./mock_media/archive}:/media/archive:rw  # 归档输出读写挂载 (:rw)
  - ${HOST_DISCARDED_DIR:-./mock_media/discarded}:/media/discarded:rw # 废弃隔离读写挂载 (:rw)
```

> **注意**：本地开发环境无需在本地运行任何容器命令（本脚手架禁止本地启动 docker/podman），容器构建验证由 GitHub Actions CI 自动执行。

---

## GHCR 容器镜像拉取与发布规范

### 镜像拉取命令

GitHub Container Registry (GHCR) 上发布的前后端容器镜像完整拉取命令如下：

```bash
# 后端镜像拉取 (将 <tag> 替换为具体发布的版本标签，如 v1.9.0)
docker pull ghcr.io/ccawmiku/video-review-cutter-backend:<tag>

# 前端镜像拉取 (将 <tag> 替换为具体发布的版本标签，如 v1.9.0)
docker pull ghcr.io/ccawmiku/video-review-cutter-frontend:<tag>
```

以版本 `v1.9.0` 为例：

```bash
docker pull ghcr.io/ccawmiku/video-review-cutter-backend:v1.9.0
docker pull ghcr.io/ccawmiku/video-review-cutter-frontend:v1.9.0
```

### 镜像发布机制说明

- **发布途径**：镜像构建与发布**仅在 GitHub Actions 持续集成自动化工作流中执行**（禁止在本地运行 Docker 进行构建或发布）。
- **触发条件**：仅在推送符合 `vMAJOR.MINOR.PATCH` 格式的带附注语义化版本标签（Annotated Semantic Version Tag，例如 `v1.9.0`）时触发发布工作流。
- **标签策略**：仅发布与 `github.ref_name` 完全匹配的显式版本标签，**绝不发布** `latest`、`stable`、`edge` 或 `nightly` 等别名标签。
- **PR CI 隔离**：Pull Request CI 构建仅执行容器构建验证（`push: false`），绝不向镜像仓库推送任何未发布的镜像。


---

## 本地开发与测试指南

### 1. 后端 (FastAPI)

#### 运行与验证

```bash
cd backend

# 安装依赖 (如使用虚拟环境)
pip install -r requirements.txt

# 代码规范检查 (Ruff)
ruff check .

# 代码格式检查 (Ruff)
ruff format --check .

# 静态类型检查 (Mypy)
mypy .

# 运行后端单元测试 (Pytest)
pytest -v

# 本地启动后端服务
uvicorn app.main:app --reload --port 8000
```

#### 健康检查接口

启动后可访问：
- API 规范文档：`http://localhost:8000/docs`
- 根健康检查：`http://localhost:8000/health`
- API 健康检查：`http://localhost:8000/api/health`

### 2. 前端 (React + Vite)

```bash
cd frontend

# 安装依赖
pnpm install

# 代码规范检查 (ESLint)
pnpm lint

# 静态类型检查 (TypeScript)
pnpm typecheck

# 运行单元测试 (Vitest)
pnpm test

# 生产环境编译构建
pnpm build

# 本地启动开发服务器
pnpm dev
```

---

## 项目目录结构

```
video-review-cutter/
├── .github/
│   └── workflows/
│       ├── ci.yml             # GitHub Actions CI 工作流 (Lint/Test/Typecheck/Docker Build)
│       └── release.yml        # GitHub Actions 发布工作流 (构建并推送 GHCR 镜像)
├── .env.example               # 环境变量配置模板
├── .gitignore                 # 安全忽略规则 (防泄露/忽略媒体、环境、缓存)
├── AGY_CLI_PROCESS_LOG.md     # 过程日志文件 (保留完整)
├── README.md                  # 项目文档
├── docker-compose.yml         # Compose 编排文件 (安全卷挂载配置)
├── backend/                   # FastAPI 后端项目
│   ├── Dockerfile
│   ├── pyproject.toml         # 后端配置与元数据 (Ruff, Mypy, Pytest)
│   ├── requirements.txt       # Python 依赖清单
│   ├── app/
│   │   ├── core/config.py     # 环境变量解析与配置管理
│   │   ├── db/session.py      # SQLite 引擎与会话工厂占位
│   │   ├── services/ffmpeg.py # FFmpeg 接口规范占位
│   │   ├── api/health.py      # 健康检查路由
│   │   ├── api/routes.py      # 路由聚合器
│   │   └── main.py            # FastAPI 应用入口与中间件
│   └── tests/
│       └── test_health.py     # 健康端点与服务占位测试
└── frontend/                  # React + TypeScript + Vite 前端项目
    ├── Dockerfile
    ├── nginx.conf             # 生产 Nginx 路由与代理配置
    ├── package.json           # 前端依赖与脚本清单
    ├── pnpm-lock.yaml         # 依赖锁定文件
    ├── tsconfig.json          # TypeScript 顶层配置
    ├── tsconfig.app.json      # 应用 TypeScript 配置
    ├── tsconfig.node.json     # Vite/Node TypeScript 配置
    ├── vite.config.ts         # Vite 与 Vitest 配置文件
    ├── tailwind.config.js     # Tailwind CSS 与设计令牌配置
    ├── postcss.config.js      # PostCSS 插件配置
    ├── eslint.config.js       # ESLint 9 扁平化规则配置
    ├── index.html             # HTML 模板入口
    ├── src/
    │   ├── main.tsx           # React 根挂载入口
    │   ├── App.tsx            # 应用主视图与状态展示
    │   ├── index.css          # 全局样式与主题变量
    │   ├── lib/utils.ts       # cn 类名合并工具函数
    │   └── components/
    │       ├── ui/            # shadcn/ui 基础设计组件 (Button, Card, Badge)
    │       └── layout/
    │           └── AppShell.tsx # 无障碍应用外壳框架
    └── tests/
        ├── setup.ts           # 测试环境初始化 (@testing-library/jest-dom)
        └── App.test.tsx       # UI 外壳与无障碍属性单元测试
```

---

## 许可证

MIT License

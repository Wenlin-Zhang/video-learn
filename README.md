# 课程教学视频处理系统

一个基于 AI 的教学视频智能处理应用，自动生成字幕、划分小节并生成规范讲义。

## 功能特性

- **语音识别**: 使用 Qwen3-ASR 模型对视频音频进行语音转文字
- **时间对齐**: 使用 Qwen3-ForcedAligner 生成精确的词级时间戳
- **字幕生成**: 自动生成 SRT 格式同步字幕文件
- **智能分节**: 调用大模型 API 自动划分课程小节
- **讲义生成**: 将口语化内容转换为规范的 Markdown 格式讲义
- **可视化界面**: 视频、字幕、讲义三栏同步显示，支持双向跳转
- **导出功能**: 支持导出 Markdown 和 Word 格式讲义

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 前端框架 | React + TypeScript + Vite |
| 语音识别 | Qwen3-ASR-0.6B |
| 时间对齐 | Qwen3-ForcedAligner-0.6B |
| 大模型 API | OpenAI 兼容接口 (Qwen3/Kimi) |
| 音频处理 | FFmpeg |

## 系统要求

- Python 3.10+
- Node.js 18+
- FFmpeg
- CUDA (可选，用于 GPU 加速)
- 8GB+ 内存 (使用 CPU) / 6GB+ 显存 (使用 GPU)

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Wenlin-Zhang/video-learn.git
cd video-learn
```

### 2. 安装后端依赖

```bash
cd backend

# 使用 uv (推荐)
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 3. 下载 ASR 模型

```bash
# 使用 ModelScope (国内推荐)
pip install modelscope
modelscope download --model Qwen/Qwen3-ASR-0.6B
modelscope download --model Qwen/Qwen3-ForcedAligner-0.6B

# 或使用 HuggingFace
huggingface-cli download Qwen/Qwen3-ASR-0.6B
huggingface-cli download Qwen/Qwen3-ForcedAligner-0.6B
```

### 4. 配置

**设置环境变量** (敏感信息不要放在配置文件中):

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，设置你的 API Key
export LLM_API_KEY="your-api-key"
# 可选：覆盖 API 端点
export LLM_API_BASE="https://api.moonshot.cn/v1"
```

**编辑 `backend/config.yaml`** (可选，调整模型配置):

```yaml
asr:
  # 使用 ModelScope 下载的模型路径
  model: "/home/<user>/.cache/modelscope/hub/models/Qwen/Qwen3-ASR-0.6B"
  aligner_model: "/home/<user>/.cache/modelscope/hub/models/Qwen/Qwen3-ForcedAligner-0.6B"
  backend: "transformers"  # "vllm" 或 "transformers"
  language: "Chinese"

llm:
  api_base: "https://api.moonshot.cn/v1"  # 或其他 OpenAI 兼容端点
  # api_key 通过环境变量 LLM_API_KEY 设置
  model: "kimi-k2.5"  # 或 "qwen3"

storage:
  upload_dir: "./uploads"
  output_dir: "./outputs"
```

### 5. 安装前端依赖

```bash
cd frontend
npm install
```

### 6. 启动服务

**启动后端** (终端 1):

```bash
cd backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 或
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**启动前端** (终端 2):

```bash
cd frontend
npm run dev
```

### 7. 访问应用

打开浏览器访问 http://localhost:3000

## 使用说明

1. **上传视频**: 点击上传区域或拖拽视频文件
2. **等待处理**: 系统自动进行语音识别、字幕生成、小节划分和讲义生成
3. **查看结果**: 
   - 左侧播放视频
   - 右侧显示同步字幕列表
   - 下方显示各小节讲义
4. **交互操作**:
   - 点击字幕条目跳转到对应视频位置
   - 点击小节卡片跳转到对应视频位置
   - 视频播放时字幕和小节自动高亮
5. **导出讲义**: 点击导出按钮下载 Markdown 或 Word 格式讲义

## 输出文件格式

### 字幕文件 (SRT)

```srt
1
00:00:01,000 --> 00:00:05,500
今天我们来学习机器学习的基本概念

2
00:00:05,800 --> 00:00:10,200
首先让我们了解什么是监督学习
```

### 讲义文件 (JSON)

```json
{
  "title": "课程标题",
  "sections": [
    {
      "id": 1,
      "title": "小节标题",
      "start_time": 0.0,
      "end_time": 120.5,
      "content": "## 小节标题\n\nMarkdown 格式内容...",
      "summary": "小节摘要"
    }
  ],
  "metadata": {
    "video_file": "lecture.mp4",
    "duration": 3600.0,
    "created_at": "2025-01-30T12:00:00"
  }
}
```

## API 接口

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/video/upload` | POST | 上传视频文件 |
| `/api/video/start/{task_id}` | POST | 开始处理任务 |
| `/api/video/status/{task_id}` | GET | 获取任务状态 |
| `/api/video/result/{task_id}` | GET | 获取处理结果 |
| `/api/video/subtitles/{task_id}` | GET | 获取字幕数据 |
| `/api/video/lecture/{task_id}` | GET | 获取讲义数据 |
| `/api/video/history` | GET | 获取历史记录 |
| `/api/video/history/{task_id}` | GET | 获取历史详情 |
| `/api/video/history/{task_id}` | DELETE | 删除历史记录 |
| `/api/video/reprocess/{task_id}` | POST | 重新处理任务 |
| `/api/export/markdown/{task_id}` | GET | 导出 Markdown |
| `/api/export/word/{task_id}` | GET | 导出 Word |
| `/ws/progress/{task_id}` | WebSocket | 实时进度推送 |

## 常见问题

### Q: 显存不足 (CUDA out of memory)

修改 `config.yaml` 将 `backend` 改为 `transformers` 并降低批处理大小，或设置环境变量:

```bash
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

### Q: 无法连接 HuggingFace

使用 HuggingFace 镜像:

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

或使用 ModelScope 下载模型后配置本地路径。

### Q: 语音识别速度慢

- 确保使用 GPU 加速
- 对于长视频，处理时间可能较长，请耐心等待

## 项目结构

```
video-learn/
├── backend/                 # Python 后端
│   ├── config.py           # 配置管理
│   ├── config.yaml         # 配置文件
│   ├── main.py             # FastAPI 入口
│   ├── models/             # 数据模型
│   ├── routers/            # API 路由
│   └── services/           # 业务服务
└── frontend/               # React 前端
    ├── src/
    │   ├── components/     # UI 组件
    │   ├── hooks/          # 自定义 Hooks
    │   ├── services/       # API 服务
    │   └── types/          # TypeScript 类型
    └── public/             # 静态资源
```

## License

MIT

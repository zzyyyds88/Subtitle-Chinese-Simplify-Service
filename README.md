# Video Converter API

## 开源声明
允许自由使用与二次开发，欢迎继续改进；但再发布或衍生作品中请保留原作者署名与项目链接。
本项目最初为自动处理 anirss 而编写，后续可能无人维护或不再更新。


## 简介
一个面向本地或局域网的**视频字幕简体化处理**服务，提供 Web UI 与 HTTP API，支持单文件与批量处理。

## 功能特性
- **HTTP API**：单文件处理、批量处理、状态查询、队列信息、文件列表
- **并行处理**：线程池并发处理，提升吞吐
- **配置灵活**：配置文件集中管理，支持前端参数覆盖
- **邮件通知**：处理完成可发送通知
- **Docker 友好**：内置 `Dockerfile` 和 `docker-compose` 模板

## 目录结构
```
video-converter/
├── api_server.py
├── video_processor_v1.py
├── index.html
├── data/
│   ├── config.json            # 本地私密配置（已加入 .gitignore）
│   └── config.example.json    # 配置示例
├── download/                  # 待处理视频目录（建议挂载）
├── Dockerfile
├── docker-compose.yml         # 本地私有配置（建议忽略）
├── docker-compose.example.yml # 公共示例
├── requirements.txt
└── README.md
```

## 快速开始（本地运行）
1. 安装依赖
```
pip install -r requirements.txt
```

2. 准备配置
```
copy data\config.example.json data\config.json
```

3. 启动服务
```
python api_server.py
```

## 快速开始（Docker）
1. 构建镜像
```
docker build -t video-converter:latest .
```

2. 运行（使用示例 compose）
```
copy docker-compose.example.yml docker-compose.yml
```
```
docker compose up -d
```

## 配置说明
- **示例配置**：`data/config.example.json`
- **本地配置**：`data/config.json`（已加入 `.gitignore`）

## API 概览
- **`POST /process`**：处理单个文件
- **`GET /status/<filename>`**：查询单文件状态
- **`GET /status`**：查询所有状态与系统信息
- **`GET /queue`**：查询并行队列信息
- **`GET /files`**：列出可处理文件
- **`POST /batch-convert`**：批量处理
- **`GET /batch-status`**：查询批量处理状态

## 请求示例
- **单文件处理**
```
POST /process
{
  "filename": "example.mp4",
  "config": {
    "replace_original": false,
    "output_suffix": "_simplified",
    "backup_original": true
  }
}
```

- **批量处理**
```
POST /batch-convert
{
  "config": {
    "replace_original": false,
    "backup_original": true
  }
}
```


# 使用Python Slim作为基础镜像（约45MB）
FROM python:3.11.6-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /app

# 更新包管理器并使用国内镜像源
RUN sed -i 's@//.*deb.debian.org@//mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's@//.*security.debian.org@//mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

# 创建非root用户（安全最佳实践）
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

# 升级pip并使用国内镜像源
RUN python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖（使用国内镜像源）
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ --no-cache-dir

# 验证zhconv安装
RUN python -c "import zhconv; print('zhconv installed successfully')"

# 复制应用程序文件
COPY . .

# 创建必要的目录并设置权限
RUN mkdir -p data download logs \
    && chown -R appuser:appuser /app \
    && chmod -R 755 /app

# 设置文件权限
RUN chmod +x /usr/bin/ffmpeg /usr/bin/ffplay /usr/bin/ffprobe

# 暴露端口
EXPOSE 5000

# 设置启动命令（以root用户运行）
CMD ["python", "api_server.py"]

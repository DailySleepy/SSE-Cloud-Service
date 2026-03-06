FROM python:3.12-slim

# 安装 uv，指定版本以保证稳定
COPY --from=ghcr.io/astral-sh/uv:0.4.15 /uv /bin/uv

# 将应用复制到容器内
COPY . /app
WORKDIR /app

# 为了安全及避免缓存问题，确保使用干净的依赖树进行安装
RUN uv sync --frozen || uv sync

# 设置环境变量，将虚拟环境的可执行文件加入 PATH (uv sync 生成的虚拟环境在 .venv 内)
ENV PATH="/app/.venv/bin:$PATH"

# 开放 FastAPI 端口
EXPOSE 8000

# 运行 FastAPI 程序
CMD ["uvicorn", "apps.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]

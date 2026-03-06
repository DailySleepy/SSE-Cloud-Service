# CourseBot

基于 FastAPI 构建并适配 openai 标准规范聊天流的后段代理服务。

## 本地启动

可以使用 `uv` 作为包管理工具进行调试：

```bash
cd coursebot
uv sync
uv run uvicorn apps.gateway.main:app --host 127.0.0.0 --port 8000 --reload
```

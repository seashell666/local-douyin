# local-douyin 后端镜像
FROM python:3.12-slim

WORKDIR /app

# 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY app ./app
COPY scripts ./scripts

# 数据目录（视频文件 + 数据库），挂载卷
RUN mkdir -p /app/data/videos

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

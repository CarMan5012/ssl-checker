FROM python:3.10-slim

# 设置工作目录
WORKDIR /app
ENV PYTHONPATH=/app

# 设置时区，方便日志查看时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制业务代码和前端模板
COPY src/ ./src/
COPY templates/ ./templates/

# 声明 Web 服务默认端口
EXPOSE 8080

# 启动 Web 管理端（程序内部启动时会自动通过多线程异步拉起定时巡检）
CMD ["python", "-u", "src/main.py"]
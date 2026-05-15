FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置时区，方便日志查看时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制业务代码
COPY ssl_check.py .

# 使用 -u 参数保证 Python 标准输出不被缓冲，方便 Docker logs 实时采集
CMD ["python", "-u", "ssl_check.py"]
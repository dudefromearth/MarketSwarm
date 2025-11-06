FROM python:3.11-slim
WORKDIR /app
# COPY services/healer/requirements.txt .   # if you have deps
# RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python", "monitor.py"]
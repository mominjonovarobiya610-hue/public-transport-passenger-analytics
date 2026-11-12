FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
ENV HOST=0.0.0.0 PORT=8080 TRANSPORT_DB=/data/transport.db
VOLUME /data
EXPOSE 8080
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", "app:application"]

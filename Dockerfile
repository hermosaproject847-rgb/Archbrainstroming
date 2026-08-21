# Optional — for hosts that use Docker instead of a native Python runtime.
FROM python:3.12-slim

WORKDIR /app
ENV MPLBACKEND=Agg PYTHONUNBUFFERED=1 PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8080
CMD ["python", "webserver.py"]

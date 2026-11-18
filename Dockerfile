FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ALADEEN_HOME=/data/.aladeen ALADEEN_HOST=0.0.0.0
WORKDIR /app

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY aladeen ./aladeen
RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8765
ENTRYPOINT ["aladeen"]
CMD ["dashboard", "--no-browser"]

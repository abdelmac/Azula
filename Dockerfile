FROM node:24.19.0-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14.7-slim-bookworm AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN python -c "import os,secrets; os.environ['DJANGO_SECRET_KEY']=secrets.token_urlsafe(64); os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; from django.core.management import execute_from_command_line; execute_from_command_line(['manage.py','collectstatic','--noinput'])"
RUN useradd --uid 10001 --create-home azula
USER azula
EXPOSE 8000
CMD ["python", "server.py"]

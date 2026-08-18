# Built on an internet-connected machine only (see deploy/offline/).
# The resulting image is fully self-contained: all Python dependencies are
# installed at build time, so the container never runs pip at runtime and
# works without any internet access.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install \
        --no-cache-dir \
        --trusted-host pypi.org \
        --trusted-host files.pythonhosted.org \
        -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

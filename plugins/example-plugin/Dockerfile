# Built on an internet-connected machine only (see deploy/offline/).
# The resulting image is self-contained and runs with no internet access,
# exactly like the Core backend image.
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

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

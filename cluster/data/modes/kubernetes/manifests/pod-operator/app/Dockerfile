FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY light-operator.py .

RUN pip install --no-cache-dir kubernetes kopf

# The SSH key is provided at runtime via a mounted Secret, not baked into the image.
ENTRYPOINT ["python", "light-operator.py"]

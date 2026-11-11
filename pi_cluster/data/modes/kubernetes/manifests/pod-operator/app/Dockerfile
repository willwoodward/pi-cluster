FROM docker.io/library/python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "kopf>=1.37,<2" "kubernetes>=29"

WORKDIR /app
COPY light-operator.py .

# The SSH key comes from a mounted Secret at runtime; it is never in the image.
ENTRYPOINT ["kopf", "run", "--standalone", "--all-namespaces", "light-operator.py"]

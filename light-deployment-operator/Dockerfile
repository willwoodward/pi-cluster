FROM python:3.8-slim

RUN apt-get update && apt-get install -y \
    openssh-client

WORKDIR /app
COPY light-operator.py .

RUN pip install kubernetes
RUN pip install kopf

COPY id_rsa /root/.ssh/id_rsa

ENTRYPOINT ["python", "light-operator.py"]

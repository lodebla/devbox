FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY host-admin/ /opt/zima-admin/
COPY bin/zima-admin /usr/local/bin/zima-admin
RUN chmod 0755 /usr/local/bin/zima-admin

CMD ["sh", "-c", "zima-admin init && exec sleep infinity"]

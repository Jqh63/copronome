# Image de l'application Copronome (Django + gunicorn).
# Base épinglée par digest (python:3.12-slim-trixie) : même Python que la CI.
# Dépendances installées avec leurs empreintes ; processus non root ;
# aucun secret ni donnée dans l'image (tout vient de COPRONOME_*).
FROM python:3.12-slim-trixie@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin copronome \
    && mkdir -p /srv/static /srv/media \
    && chown copronome:copronome /srv/static /srv/media

COPY --chown=root:root . .
RUN chmod 0755 docker/entrypoint.sh

ENV COPRONOME_STATIC_ROOT=/srv/static \
    COPRONOME_MEDIA_ROOT=/srv/media

USER copronome
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["web"]

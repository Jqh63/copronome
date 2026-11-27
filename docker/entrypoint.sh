#!/bin/sh
# Démarrage du conteneur Copronome. Rôles :
#   migrer   (rôle Postgres propriétaire, service ponctuel) migrations, table
#            de cache, rôle restreint de l'app et ses droits
#   web      fichiers statiques, puis gunicorn (rôle Postgres restreint)
#   rappels  `envoyer_rappels` au démarrage puis toutes les
#            COPRONOME_RAPPELS_INTERVALLE secondes (la commande est idempotente
#            dans la journée) ; une ligne horodatée par passe = signe de vie
#   sante    sonde de la healthcheck (GET /sante/ en local)
#   autre    passé tel quel à manage.py (ex. `inviter`, `charger_demo`)
# gunicorn n'écrit aucun journal d'accès : les URL portent des jetons (iCal,
# invitation, réinitialisation) ; le journal d'accès est celui de Caddy, filtré.
set -eu

case "${1:-web}" in
migrer)
    python manage.py migrate --noinput
    python manage.py createcachetable
    exec python manage.py appliquer_droits_base
    ;;
web)
    python manage.py collectstatic --noinput --clear --verbosity 0
    exec gunicorn copronome.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${COPRONOME_GUNICORN_WORKERS:-2}" \
        --worker-tmp-dir /dev/shm \
        --error-logfile -
    ;;
rappels)
    intervalle="${COPRONOME_RAPPELS_INTERVALLE:-86400}"
    while :; do
        if python manage.py envoyer_rappels --url "${COPRONOME_URL_PUBLIQUE:-}"; then
            echo "$(date -Iseconds) rappels : passe terminée"
        else
            echo "$(date -Iseconds) rappels : ECHEC de la passe" >&2
        fi
        sleep "$intervalle"
    done
    ;;
sante)
    exec python - <<'EOF'
import os, sys, urllib.request
hote = os.environ.get("COPRONOME_ALLOWED_HOSTS", "localhost").split(",")[0].strip()
req = urllib.request.Request(
    "http://127.0.0.1:8000/sante/",
    headers={"Host": hote, "X-Forwarded-Proto": "https"},
)
try:
    with urllib.request.urlopen(req, timeout=5) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
EOF
    ;;
*)
    exec python manage.py "$@"
    ;;
esac

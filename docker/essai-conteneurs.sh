#!/usr/bin/env bash
# Essai de bout en bout du compose.yaml (CI, ou à la main avec Docker) :
# construit, démarre, puis vérifie à travers Caddy la sonde, les en-têtes de
# sécurité, les fichiers statiques, la limite de corps (413), l'absence de
# jeton dans le journal (avec contrôle positif du masquage), le rôle Postgres
# restreint de l'app et le signe de vie des rappels. Projet compose isolé,
# détruit à la sortie (volumes compris).
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=copronome-essai
export COPRONOME_SECRET_KEY="essai-$(openssl rand -hex 24)"
export COPRONOME_DB_PASSWORD="essai-$(openssl rand -hex 12)"
export COPRONOME_DB_APP_PASSWORD="essai-$(openssl rand -hex 12)"
export COPRONOME_PORT_HTTPS=18443
export COPRONOME_URL_PUBLIQUE=https://localhost:18443
export COPRONOME_DOCUMENT_TAILLE_MAX_MO=2
export COPRONOME_CORPS_MAX_MO=3
URL=https://localhost:18443

echec() { echo "ECHEC : $*" >&2; docker compose logs --no-color --tail 80 >&2 || true; exit 1; }
trap 'docker compose down -v --remove-orphans >/dev/null 2>&1 || true' EXIT

docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180 || echec "démarrage"

code=$(curl -sk -o /tmp/sante.json -w '%{http_code}' "$URL/sante/")
[ "$code" = 200 ] || echec "sonde : HTTP $code"
grep -q '"ok"' /tmp/sante.json || echec "sonde : corps inattendu"

entetes=$(curl -sk -D - -o /dev/null "$URL/compte/login/")
for e in content-security-policy strict-transport-security x-content-type-options; do
    grep -qi "^$e:" <<<"$entetes" || echec "en-tête $e absent"
done

css=$(cd copronome/static && find . -name '*.css' -print -quit)
[ -n "$css" ] || echec "aucune feuille de style dans copronome/static"
code=$(curl -sk -o /dev/null -w '%{http_code}' "$URL/static/${css#./}")
[ "$code" = 200 ] || echec "statique ${css#./} : HTTP $code"

head -c $((4 * 1024 * 1024)) /dev/zero >/tmp/gros.bin
code=$(curl -sk -o /dev/null -w '%{http_code}' --data-binary @/tmp/gros.bin "$URL/documents/")
[ "$code" = 413 ] || echec "corps de 4 Mio : HTTP $code au lieu de 413"

jeton="JETONESSAI$(openssl rand -hex 8)"
curl -sk -o /dev/null "$URL/agenda/ical/$jeton/"
curl -sk -o /dev/null -H "Referer: $URL/invitation/$jeton/" "$URL/invitation/$jeton/"
sleep 1
journal=$(docker compose logs --no-color caddy app)
if grep -q "$jeton" <<<"$journal"; then echec "jeton présent dans le journal"; fi
grep -q '/agenda/ical/\[jeton\]' <<<"$journal" || echec "contrôle positif : URI masquée absente du journal"

# L'app tourne sous le rôle restreint : ni superutilisateur, ni UPDATE,
# DELETE ou TRUNCATE sur le journal d'audit ; INSERT = contrôle positif.
role=$(docker compose exec -T app python manage.py shell <<'PY'
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user")
    nom, superu = c.fetchone()
    c.execute(
        "SELECT has_table_privilege('audit_journalaudit', 'UPDATE'),"
        " has_table_privilege('audit_journalaudit', 'DELETE'),"
        " has_table_privilege('audit_journalaudit', 'TRUNCATE'),"
        " has_table_privilege('audit_journalaudit', 'INSERT')"
    )
    print("ROLE=%s SUPER=%s UPDATE=%s DELETE=%s TRUNCATE=%s INSERT=%s" % (nom, superu, *c.fetchone()))
PY
) || echec "rôle de l'app : shell en échec"
attendu="ROLE=copronome_app SUPER=False UPDATE=False DELETE=False TRUNCATE=False INSERT=True"
grep -qF "$attendu" <<<"$role" || echec "rôle de l'app : $role"

vivant=""
for _ in $(seq 1 30); do
    rappels=$(docker compose logs --no-color rappels)
    if grep -q 'rappels : passe terminée' <<<"$rappels"; then vivant=1; break; fi
    sleep 2
done
[ -n "$vivant" ] || echec "rappels : aucun signe de vie"

echo "essai des conteneurs : OK"

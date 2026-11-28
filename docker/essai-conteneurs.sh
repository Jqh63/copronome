#!/usr/bin/env bash
# Essai de bout en bout du compose.yaml (CI, ou à la main avec Docker) :
# construit, démarre, puis vérifie à travers Caddy la sonde, les en-têtes de
# sécurité, les fichiers statiques servis par l'app, la limite de corps (413), l'absence de
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
# Noms de base et de rôles d'une instance, autres que les défauts : prouve
# que rien ne reste câblé sur « copronome ».
export COPRONOME_DB_NAME=base_essai
export COPRONOME_DB_OWNER=proprio_essai
export COPRONOME_DB_APP_USER=app_essai
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

# Statiques servis par l'app (WhiteNoise) : la page cite le nom haché, servi
# avec un cache immuable ; Caddy ne fait que relayer.
# Page publique qui étend base.html (les pages allauth ont leur propre gabarit).
page=$(curl -sk "$URL/invitation/inexistante/")
css=$(grep -o '/static/[^"]*\.css' <<<"$page" | head -1 || true)
[ -n "$css" ] || echec "aucune feuille de style citée par /invitation/inexistante/ : $(grep -i -m3 'stylesheet\|<title' <<<"$page" || head -c 300 <<<"$page")"
grep -qE '^/static/copronome\.[0-9a-f]{12}\.css$' <<<"$css" || echec "feuille de style non hachée : '${css}'"
entetes_css=$(curl -sk -D - -o /dev/null -H 'Accept-Encoding: gzip' "$URL$css")
grep -q '^HTTP/[0-9.]* 200' <<<"$entetes_css" || echec "statique $css : $(head -1 <<<"$entetes_css")"
grep -qi '^cache-control:.*immutable' <<<"$entetes_css" || echec "statique $css : pas de cache immuable"

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
    c.execute(
        "SELECT current_user, rolsuper, current_database() FROM pg_roles WHERE rolname = current_user"
    )
    nom, superu, base = c.fetchone()
    c.execute(
        "SELECT has_table_privilege('audit_journalaudit', 'UPDATE'),"
        " has_table_privilege('audit_journalaudit', 'DELETE'),"
        " has_table_privilege('audit_journalaudit', 'TRUNCATE'),"
        " has_table_privilege('audit_journalaudit', 'INSERT')"
    )
    print("BASE=%s ROLE=%s SUPER=%s UPDATE=%s DELETE=%s TRUNCATE=%s INSERT=%s" % (base, nom, superu, *c.fetchone()))
PY
) || echec "rôle de l'app : shell en échec"
attendu="BASE=base_essai ROLE=app_essai SUPER=False UPDATE=False DELETE=False TRUNCATE=False INSERT=True"
grep -qF "$attendu" <<<"$role" || echec "rôle de l'app : $role"

# Cookies d'une instance sous un domaine partagé : préfixe __Host-, Secure,
# Path=/, sans Domain (ADR domaine et instances, § 3).
cookie=$(curl -sk -D - -o /dev/null "$URL/compte/login/" | grep -i '^set-cookie: __Host-csrftoken=') ||
    echec "cookie CSRF __Host- absent"
grep -qi 'secure' <<<"$cookie" && grep -qi 'path=/' <<<"$cookie" || echec "cookie CSRF : $cookie"
if grep -qi 'domain=' <<<"$cookie"; then echec "cookie CSRF avec Domain : $cookie"; fi

vivant=""
for _ in $(seq 1 30); do
    rappels=$(docker compose logs --no-color rappels)
    if grep -q 'rappels : passe terminée' <<<"$rappels"; then vivant=1; break; fi
    sleep 2
done
[ -n "$vivant" ] || echec "rappels : aucun signe de vie"

echo "essai des conteneurs : OK"

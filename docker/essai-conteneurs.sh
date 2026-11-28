#!/usr/bin/env bash
# Essai de bout en bout (CI, ou à la main avec Docker) : un registre de deux
# instances, créées par exploitation/creer.py, derrière le frontal généré par
# exploitation/frontal.py. Vérifie le routage par nom d'hôte (chaque nom
# atteint sa copropriété), l'ancien slug redirigé, le nom inconnu refusé,
# l'absence de port publié par les instances, puis à travers le frontal la
# sonde, les en-têtes de sécurité, les statiques servis par l'app, la limite
# de corps (413), l'absence de jeton dans le journal (avec contrôle positif),
# le rôle Postgres restreint, les cookies __Host- et les rappels. Projets
# compose isolés, détruits à la sortie (volumes compris).
set -euo pipefail
cd "$(dirname "$0")/.."

HTTPS=18443
HTTP=18080
DOMAINE=copro.example.org
A=iessai0000000a
B=iessai0000000b
HOTE_A="tilleuls-essai.$DOMAINE"
HOTE_B="parc-essai.$DOMAINE"
ANCIEN_A="ancien-tilleuls-essai.$DOMAINE"

racine=$(mktemp -d)
mkdir "$racine/conf"
export COPRONOME_FRONTAL_CONF="$racine/conf" COPRONOME_FRONTAL_HTTPS=$HTTPS COPRONOME_FRONTAL_HTTP=$HTTP
export COPRONOME_CORPS_MAX_MO=3
frontal() { docker compose -f frontal/compose.yaml -p copronome-essai-frontal "$@"; }
instance() { local id=$1; shift; docker compose -p "copronome-essai-$id" --env-file "$racine/$id/instance.env" "$@"; }
# curl vers le frontal local, sous le nom d'hôte demandé (SNI et Host).
requete() { local hote=$1 chemin=$2; shift 2; curl -sk --resolve "$hote:$HTTPS:127.0.0.1" "$@" "https://$hote:$HTTPS$chemin"; }

echec() {
    echo "ECHEC : $*" >&2
    frontal logs --no-color --tail 40 >&2 || true
    for id in $A $B; do instance "$id" logs --no-color --tail 40 >&2 || true; done
    exit 1
}
menage() {
    for id in $A $B; do instance "$id" down -v --remove-orphans >/dev/null 2>&1 || true; done
    frontal down -v --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$racine"
}
trap menage EXIT

cat >"$racine/registre.toml" <<EOF
version = 1
domaine = "$DOMAINE"

[[instance]]
id = "$A"
slug = "tilleuls-essai"
nom = "Essai A"
commune = "Exempleville"
etat = "active"
anciens_slugs = ["ancien-tilleuls-essai"]

[[instance]]
id = "$B"
slug = "parc-essai"
nom = "Essai B"
commune = "Exempleville"
etat = "active"
EOF

python3 -m exploitation.creer "$racine/registre.toml" "$racine" >/dev/null || echec "création des instances"
# Variable ajoutée à la main, gardée au rejeu ; petite limite pour le 413.
echo "COPRONOME_DOCUMENT_TAILLE_MAX_MO=2" >>"$racine/$A/instance.env"
rejeu=$(python3 -m exploitation.creer "$racine/registre.toml" "$racine")
grep -q "$A (tilleuls-essai) : inchangée" <<<"$rejeu" || echec "rejeu de la création : $rejeu"
python3 -m exploitation.frontal "$racine/registre.toml" "$racine/conf/Caddyfile" --tls-interne >/dev/null

frontal config --quiet
frontal up -d --wait --wait-timeout 60 || echec "démarrage du frontal"
for id in $A $B; do
    instance "$id" config --quiet
    conf=$(instance "$id" config)
    if grep -qE '^\s+published:' <<<"$conf"; then echec "instance $id : port publié"; fi
    instance "$id" up -d --build --wait --wait-timeout 180 || echec "démarrage de l'instance $id"
done
instance $B exec -T app python manage.py copropriete --nom "Essai B" --commune Exempleville --code-insee 99999 \
    >/dev/null || echec "identité de B"

# Routage : chaque nom atteint sa copropriété, et pas l'autre.
page_a=$(requete "$HOTE_A" /invitation/inexistante/)
page_b=$(requete "$HOTE_B" /invitation/inexistante/)
grep -q 'Essai B' <<<"$page_b" || echec "B : titre « Essai B » absent : $(grep -m1 '<title' <<<"$page_b")"
if grep -q 'Essai B' <<<"$page_a"; then echec "le nom de A sert la page de B"; fi

code=$(requete "$HOTE_A" /sante/ -o /tmp/sante.json -w '%{http_code}')
[ "$code" = 200 ] || echec "sonde A : HTTP $code"
grep -q '"ok"' /tmp/sante.json || echec "sonde A : corps inattendu"

loc=$(requete "$ANCIEN_A" /sante/?x=1 -o /dev/null -w '%{http_code} %{redirect_url}')
[ "$loc" = "308 https://$HOTE_A/sante/?x=1" ] || echec "ancien slug : $loc"

# Nom inconnu : pas de certificat en HTTPS, connexion fermée en HTTP.
if requete "inconnu.$DOMAINE" /sante/ -o /dev/null; then echec "nom inconnu servi en HTTPS"; fi
if curl -s -o /dev/null -H "Host: inconnu.$DOMAINE" "http://127.0.0.1:$HTTP/"; then
    echec "nom inconnu servi en HTTP"
fi
# Nom TLS de A, en-tête Host de B : refusé (strict_sni_host).
code=$(requete "$HOTE_A" /sante/ -H "Host: $HOTE_B" -o /dev/null -w '%{http_code}' || true)
[ "$code" = 421 ] || echec "SNI de A, Host de B : HTTP $code au lieu de 421"

entetes=$(requete "$HOTE_A" /compte/login/ -D - -o /dev/null)
for e in content-security-policy strict-transport-security x-content-type-options; do
    grep -qi "^$e:" <<<"$entetes" || echec "en-tête $e absent"
done

# Statiques servis par l'app (WhiteNoise) : la page cite le nom haché, servi
# avec un cache immuable ; le frontal ne fait que relayer.
css=$(grep -o '/static/[^"]*\.css' <<<"$page_a" | head -1 || true)
[ -n "$css" ] || echec "aucune feuille de style citée : $(head -c 300 <<<"$page_a")"
grep -qE '^/static/copronome\.[0-9a-f]{12}\.css$' <<<"$css" || echec "feuille de style non hachée : '${css}'"
entetes_css=$(requete "$HOTE_A" "$css" -D - -o /dev/null -H 'Accept-Encoding: gzip')
grep -q '^HTTP/[0-9.]* 200' <<<"$entetes_css" || echec "statique $css : $(head -1 <<<"$entetes_css")"
grep -qi '^cache-control:.*immutable' <<<"$entetes_css" || echec "statique $css : pas de cache immuable"

head -c $((4 * 1024 * 1024)) /dev/zero >/tmp/gros.bin
code=$(requete "$HOTE_A" /documents/ -o /dev/null -w '%{http_code}' --data-binary @/tmp/gros.bin)
[ "$code" = 413 ] || echec "corps de 4 Mio : HTTP $code au lieu de 413"

jeton="JETONESSAI$(openssl rand -hex 8)"
requete "$HOTE_A" "/agenda/ical/$jeton/" -o /dev/null
requete "$HOTE_A" "/invitation/$jeton/" -o /dev/null -H "Referer: https://$HOTE_A/invitation/$jeton/"
sleep 1
journal=$(frontal logs --no-color caddy; instance $A logs --no-color app)
if grep -q "$jeton" <<<"$journal"; then echec "jeton présent dans le journal"; fi
grep -q '/agenda/ical/\[jeton\]' <<<"$journal" || echec "contrôle positif : URI masquée absente du journal"

# Rechargement à chaud : régénéré sans changement, puis rechargé, A répond.
regen=$(python3 -m exploitation.frontal "$racine/registre.toml" "$racine/conf/Caddyfile" --tls-interne)
grep -q inchangé <<<"$regen" || echec "régénération du frontal : $regen"
frontal exec -T caddy caddy reload --config /etc/caddy/Caddyfile || echec "rechargement du frontal"
code=$(requete "$HOTE_A" /sante/ -o /dev/null -w '%{http_code}')
[ "$code" = 200 ] || echec "après rechargement : HTTP $code"

# L'app tourne sous le rôle restreint de son instance : ni superutilisateur,
# ni UPDATE, DELETE ou TRUNCATE sur le journal d'audit ; INSERT = contrôle positif.
role=$(instance $A exec -T app python manage.py shell <<'PY'
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
attendu="BASE=copronome_$A ROLE=copronome_${A}_app SUPER=False UPDATE=False DELETE=False TRUNCATE=False INSERT=True"
grep -qF "$attendu" <<<"$role" || echec "rôle de l'app : $role"

# Cookies d'une instance sous un domaine partagé : préfixe __Host-, Secure,
# Path=/, sans Domain (ADR domaine et instances, § 3).
cookie=$(requete "$HOTE_A" /compte/login/ -D - -o /dev/null | grep -i '^set-cookie: __Host-csrftoken=') ||
    echec "cookie CSRF __Host- absent"
grep -qi 'secure' <<<"$cookie" && grep -qi 'path=/' <<<"$cookie" || echec "cookie CSRF : $cookie"
if grep -qi 'domain=' <<<"$cookie"; then echec "cookie CSRF avec Domain : $cookie"; fi

vivant=""
for _ in $(seq 1 30); do
    rappels=$(instance $A logs --no-color rappels)
    if grep -q 'rappels : passe terminée' <<<"$rappels"; then vivant=1; break; fi
    sleep 2
done
[ -n "$vivant" ] || echec "rappels : aucun signe de vie"

echo "essai des conteneurs : OK"

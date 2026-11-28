# Copronome

Logiciel libre de gestion de copropriété, pensé pour le **conseil syndical** et le **syndic coopératif** (ou bénévole).

> Statut : en construction — aucune version utilisable pour l'instant.

## Ce que Copronome veut faire

Par couches, dans cet ordre :

1. **Fonctionnement du conseil syndical** : bâtiments, lots et tantièmes, personnes, incidents et suivi des demandes au syndic, documents, agenda, échéances réglementaires, relevés d'index des compteurs d'eau (tournée par bâtiment, index en baisse signalés, m³ par lot exportés pour la clé eau du logiciel de comptabilité ; Copronome ne répartit pas l'eau en euros).
2. **Syndic coopératif** : assemblées générales (convocation, vote par correspondance, majorités, procès-verbal), contrats, sinistres, carnet d'entretien.
3. **Comptabilité** : d'abord par interfaçage avec [Diacamma Syndic](https://www.diacamma.org/), logiciel libre existant.

Copronome ne rend jamais obligatoire un accès numérique : tout document se génère en PDF imprimable, et un vote papier se saisit.

## Principes

- **Une instance par copropriété** : chaque copropriété a sa propre base, ses fichiers et sa configuration.
- **Aucune donnée réelle dans ce dépôt** : uniquement des données de démonstration fictives.
- **Réversibilité** : export complet lisible sans l'application.
- **Sécurité** : comptes sur invitation, second facteur pour les rôles qui écrivent, contrôle d'accès centralisé et testé.

## Stack prévue

Python / Django, Postgres, htmx, Caddy, déploiement par Docker Compose.

## Développer

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest -q
COPRONOME_DEBUG=1 .venv/bin/python manage.py migrate
COPRONOME_DEBUG=1 .venv/bin/python manage.py charger_demo --activite   # base vide seulement
COPRONOME_DEBUG=1 .venv/bin/python manage.py runserver
```

`charger_demo` crée une résidence fictive : 3 bâtiments, 32 lots (logements, caves, parkings),
les clés générale, bâtiment, escalier, ascenseur, portail, chaudières et stationnements. `--activite`
y ajoute des échéances, des incidents, des rendez-vous et des relevés d'eau datés autour du jour du chargement.

Essai dans un vrai navigateur (Chromium sans tête, joué aussi par la CI) : invitation, second facteur
(code TOTP ou clé d'accès simulée), incident, reconnexion.

```bash
.venv/bin/python -m playwright install chromium-headless-shell
.venv/bin/pytest -q tests_navigateur
```

En production, la configuration se lit dans les variables `COPRONOME_*` (modèle : `env.exemple`).

## Lancer avec Docker Compose

`compose.yaml` démarre une instance : l'app (gunicorn, fichiers statiques compris) et les rappels d'échéances quotidiens, suivis de la purge des anciens copropriétaires et occupants : coordonnées effacées 5 ans après la fin de leur dernier lien avec un lot (délai de prescription, loi de 1965 art. 42 et code civil art. 2224 ; détail dans `copro/purge.py`), jamais pour une personne liée à un compte actif. L'instance ne publie aucun port : le frontal (`frontal/compose.yaml`, un Caddy par serveur) joint l'app par le réseau partagé `copronome-frontal`. Sa base vit dans le cluster Postgres du serveur (`postgres/compose.yaml`, un par serveur), joint par le réseau interne `copronome-base`, sans sortie. Un service ponctuel `migrer` applique les migrations sous le rôle Postgres propriétaire de la base, puis donne au rôle restreint de l'app ses droits (`manage.py appliquer_droits_base`) : ni superutilisateur ni propriétaire, sans UPDATE ni DELETE sur les journaux (audit, incidents, échéances, relevés d'eau), qu'un trigger protège aussi.

Les instances se créent depuis le registre (section suivante) ; pour essayer en local, un registre d'une instance sous `copro.localhost` suffit (les navigateurs résolvent `*.localhost` vers la machine) :

```bash
python -m exploitation.creer registre.toml instances/          # instances/<id>/instance.env
mkdir -p frontal/conf && python -m exploitation.frontal registre.toml frontal/conf/Caddyfile --tls-interne
COPRONOME_FRONTAL_CONF=$PWD/frontal/conf docker compose -f frontal/compose.yaml up -d   # d'abord : crée le réseau
python -m exploitation.postgres configurer registre.toml instances/   # instances/_cluster/{conf/pg_hba.conf,postgres.env}
COPRONOME_POSTGRES_CONF=$PWD/instances/_cluster/conf docker compose -f postgres/compose.yaml \
  --env-file instances/_cluster/postgres.env up -d --wait          # d'abord aussi : crée le réseau de la base
python -m exploitation.postgres sql instances/<id>/instance.env |
  docker compose -f postgres/compose.yaml exec -T -u postgres postgres psql -q -d postgres   # rôles et base, rejouable
docker compose -p copronome-<id> --env-file instances/<id>/instance.env up -d --build
docker compose -p copronome-<id> --env-file instances/<id>/instance.env run --rm app copropriete --nom "<nom>" --commune "<commune>" --code-insee <code>
docker compose -p copronome-<id> --env-file instances/<id>/instance.env run --rm app inviter ...   # toute commande manage.py
docker/essai-conteneurs.sh                                    # essai de bout en bout, deux instances (rejoué en CI)
```

`copropriete` saisit l'identité de l'instance (nom, commune et code INSEE, adresse, numéro d'immatriculation au registre national), affichée dans les pages, l'objet et l'expéditeur des mails (« <nom> via Copronome ») et le nom du calendrier iCal ; rejouable, elle ne crée jamais un second enregistrement. Tant qu'elle n'est pas saisie, l'instance s'affiche « Copronome ».

Variables propres au déploiement (défaut entre parenthèses) : `COPRONOME_DOMAINE` (`localhost`), `COPRONOME_URL_PUBLIQUE` (`https://localhost:8443`), `COPRONOME_RAPPELS_INTERVALLE` (`86400` secondes), `COPRONOME_GUNICORN_WORKERS` (`2`), `COPRONOME_TRUSTED_PROXY_COUNT` (`1` derrière le frontal : IP du client pour la limite de tentatives de connexion), `COPRONOME_INSTANCE_ID` (`local`), `COPRONOME_DB_NAME` et `COPRONOME_DB_OWNER` (`copronome`). Plusieurs instances sous un même domaine (`<slug>.example.org`) : hôtes autorisés et origines CSRF sont un nom exact (joker refusé au démarrage), les cookies portent le préfixe `__Host-` (ni `Domain`, ni partage entre sous-domaines) et seuls le propriétaire et le rôle de l'app se connectent à la base (`REVOKE CONNECT … FROM PUBLIC`). Le journal d'accès du frontal masque les jetons des URL (iCal, invitation, réinitialisation, confirmation) ; gunicorn n'en écrit pas.

## Héberger plusieurs copropriétés : le registre des instances

Chaque copropriété est une instance (sa base, ses fichiers, son adresse `https://<slug>.<domaine>`). Le registre des instances est un fichier TOML, une table `[[instance]]` par copropriété : identifiant opaque et immuable (il nomme la base, les rôles, les volumes et les sauvegardes), slug, nom, commune, état (`active`, `suspendue`, `supprimee`), anciens slugs. Un slug n'est jamais réattribué, même après une suppression ou un renommage ; les slugs d'infrastructure (`www`, `admin`, `api`, `mail`…) sont réservés. Le registre réel nomme des copropriétés : gardez-le hors du dépôt. Le modèle fictif est `exploitation/registre.exemple.toml`.

```bash
python -m exploitation.registre verifier <registre.toml>   # 0 = valide ; sinon toutes les erreurs
python -m exploitation.registre nouvel-id                  # identifiant d'une nouvelle instance
python -m exploitation.creer <registre.toml> <racine> [<id> ...]   # crée ou recale <racine>/<id>/instance.env
python -m exploitation.frontal <registre.toml> <conf>/Caddyfile [--tls-interne]   # configuration du frontal
docker compose -f frontal/compose.yaml exec caddy caddy reload --config /etc/caddy/Caddyfile
python -m exploitation.postgres configurer <registre.toml> <racine>   # pg_hba du cluster et secret du superutilisateur
python -m exploitation.postgres sql <racine>/<id>/instance.env       # SQL des rôles et de la base, pour psql
```

`creer` est idempotent : pour chaque instance active (ou celles nommées), il écrit `<racine>/<id>/instance.env` (mode 600) avec les variables du contrat dérivées du registre (identifiant, `COPRONOME_DOMAINE` = `<slug>.<domaine>`, URL publique, base et rôles Postgres `copronome_<id>` et `copronome_<id>_app`) et des secrets propres à l'instance (`SECRET_KEY`, mots de passe des deux rôles), générés une seule fois et jamais régénérés. Rejoué après un renommage, il recale l'adresse sans toucher aux secrets ; une variable ajoutée à la main (identifiants mail) est conservée.

`postgres configurer` écrit la configuration du cluster sous `<racine>/_cluster/` : `conf/pg_hba.conf`, généré depuis le registre (chaque base n'accepte que ses deux rôles, `scram-sha-256` ; le superutilisateur n'entre que par la socket locale du conteneur ; tout le reste est refusé), et `postgres.env` (mode 600), mot de passe du superutilisateur généré une fois, que l'image exige à l'initialisation et que le `pg_hba` rend inutilisable par le réseau. Après un changement du registre (instance créée ou supprimée) : rejouer `configurer`, puis `docker compose -f postgres/compose.yaml exec -u postgres postgres psql -c 'SELECT pg_reload_conf()'`. `postgres sql` écrit le SQL idempotent qui crée ou recale les deux rôles de l'instance (sans attribut d'administration, mots de passe de `instance.env`) et sa base (propriétaire, `REVOKE ALL … FROM PUBLIC`, `CONNECT` pour le rôle de l'app) ; il passe à `psql` par l'entrée standard, jamais en argument. Limites assumées (ADR) : un cluster par serveur partage les mises à jour majeures et le plafond de connexions (`max_connections`, 100 par défaut, environ `COPRONOME_GUNICORN_WORKERS` + 2 par instance) ; sur le réseau de la base, comme sur celui du frontal, une instance joint l'app des autres en direct.

`frontal` génère le Caddyfile du frontal : un bloc par instance active (proxy vers l'alias `copronome-<id>`), une redirection 308 par ancien slug, 503 pour une instance suspendue ; une instance supprimée ou un nom inconnu n'obtient rien (pas de certificat en HTTPS, connexion fermée en HTTP). Le nom TLS doit égaler l'en-tête `Host` (`strict_sni_host`). Le fichier n'est réécrit que s'il change, puis `caddy reload` l'applique à chaud ; le frontal n'a ni socket Docker ni état propre. `COPRONOME_CORPS_MAX_MO` (`21`) borne le corps des requêtes au frontal, à garder au-dessus de `COPRONOME_DOCUMENT_TAILLE_MAX_MO` ; `COPRONOME_FRONTAL_HTTP` et `COPRONOME_FRONTAL_HTTPS` (`80`, `443`) choisissent les ports publiés. Limite assumée : sur le réseau du frontal, une instance joint l'app des autres directement, sans passer par le frontal.

## Contribuer : aucun secret, aucune donnée réelle

Avant le premier commit, dans votre clone :

```bash
git config core.hooksPath .githooks   # active le contrôle avant commit
```

Le hook refuse un commit qui contient un secret, un IBAN, un numéro de téléphone ou une adresse mail hors domaines fictifs (`.gitleaks.toml`, avec [gitleaks](https://github.com/gitleaks/gitleaks) installé). Il vérifie aussi les termes privés de votre copropriété (nom, adresse, noms des personnes), listés un par ligne **hors du dépôt**, dans `~/.config/copronome/termes-prives.txt`. La CI rejoue le même scan sur chaque PR.

Toute contribution extérieure suppose l'acceptation de l'[accord de contribution](CLA.md) : vous restez auteur, et le mainteneur peut aussi licencier votre contribution sous d'autres conditions que l'AGPL. Les licences des dépendances sont inventoriées dans [`LICENCES-DEPENDANCES.md`](LICENCES-DEPENDANCES.md), à tenir à jour avec `requirements.txt`.

## Licence

[AGPL-3.0](LICENSE) : si vous proposez une version modifiée de Copronome en service à d'autres personnes, vous devez en publier le code source.

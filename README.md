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

`compose.yaml` démarre l'app (gunicorn), Postgres, Caddy (TLS, fichiers statiques) et les rappels d'échéances quotidiens, suivis de la purge des anciens copropriétaires et occupants : coordonnées effacées 5 ans après la fin de leur dernier lien avec un lot (délai de prescription, loi de 1965 art. 42 et code civil art. 2224 ; détail dans `copro/purge.py`), jamais pour une personne liée à un compte actif. Seul Caddy est publié ; la base n'a aucune sortie réseau. Un service ponctuel `migrer` applique les migrations sous le rôle Postgres propriétaire, puis crée le rôle restreint de l'app (`manage.py appliquer_droits_base`) : ni superutilisateur ni propriétaire, sans UPDATE ni DELETE sur les journaux (audit, incidents, échéances, relevés d'eau), qu'un trigger protège aussi.

```bash
# .env à côté de compose.yaml (jamais versionné), au minimum :
#   COPRONOME_SECRET_KEY=<clé longue et aléatoire>
#   COPRONOME_DB_PASSWORD=<mot de passe du rôle propriétaire de la base>
#   COPRONOME_DB_APP_PASSWORD=<mot de passe du rôle de l'app>
docker compose up -d --build                  # https://localhost:8443 (CA interne de Caddy)
docker compose run --rm app copropriete --nom "<nom>" --commune "<commune>" --code-insee <code>
docker compose run --rm app inviter ...       # toute commande manage.py
docker/essai-conteneurs.sh                    # essai de bout en bout (rejoué en CI)
```

`copropriete` saisit l'identité de l'instance (nom, commune et code INSEE, adresse, numéro d'immatriculation au registre national), affichée dans les pages, l'objet et l'expéditeur des mails (« <nom> via Copronome ») et le nom du calendrier iCal ; rejouable, elle ne crée jamais un second enregistrement. Tant qu'elle n'est pas saisie, l'instance s'affiche « Copronome ».

Variables propres au déploiement (défaut entre parenthèses) : `COPRONOME_DOMAINE` (`localhost`), `COPRONOME_URL_PUBLIQUE` (`https://localhost:8443`), `COPRONOME_PORT_HTTPS` (`8443`), `COPRONOME_CORPS_MAX_MO` (`21`, limite de corps de Caddy, à garder au-dessus de `COPRONOME_DOCUMENT_TAILLE_MAX_MO`), `COPRONOME_RAPPELS_INTERVALLE` (`86400` secondes), `COPRONOME_GUNICORN_WORKERS` (`2`), `COPRONOME_TRUSTED_PROXY_COUNT` (`1` derrière Caddy : IP du client pour la limite de tentatives de connexion), `COPRONOME_INSTANCE_ID` (`local`), `COPRONOME_DB_NAME` et `COPRONOME_DB_OWNER` (`copronome`). Plusieurs instances sous un même domaine (`<slug>.example.org`) : hôtes autorisés et origines CSRF sont un nom exact (joker refusé au démarrage), les cookies portent le préfixe `__Host-` (ni `Domain`, ni partage entre sous-domaines) et seuls le propriétaire et le rôle de l'app se connectent à la base (`REVOKE CONNECT … FROM PUBLIC`). Le journal d'accès de Caddy masque les jetons des URL (iCal, invitation, réinitialisation, confirmation) ; gunicorn n'en écrit pas.

## Contribuer : aucun secret, aucune donnée réelle

Avant le premier commit, dans votre clone :

```bash
git config core.hooksPath .githooks   # active le contrôle avant commit
```

Le hook refuse un commit qui contient un secret, un IBAN, un numéro de téléphone ou une adresse mail hors domaines fictifs (`.gitleaks.toml`, avec [gitleaks](https://github.com/gitleaks/gitleaks) installé). Il vérifie aussi les termes privés de votre copropriété (nom, adresse, noms des personnes), listés un par ligne **hors du dépôt**, dans `~/.config/copronome/termes-prives.txt`. La CI rejoue le même scan sur chaque PR.

Toute contribution extérieure suppose l'acceptation de l'[accord de contribution](CLA.md) : vous restez auteur, et le mainteneur peut aussi licencier votre contribution sous d'autres conditions que l'AGPL. Les licences des dépendances sont inventoriées dans [`LICENCES-DEPENDANCES.md`](LICENCES-DEPENDANCES.md), à tenir à jour avec `requirements.txt`.

## Licence

[AGPL-3.0](LICENSE) : si vous proposez une version modifiée de Copronome en service à d'autres personnes, vous devez en publier le code source.

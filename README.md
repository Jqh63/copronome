# Copronome

Logiciel libre de gestion de copropriété, pensé pour le **conseil syndical** et le **syndic coopératif** (ou bénévole).

> Statut : en construction — aucune version utilisable pour l'instant.

## Ce que Copronome veut faire

Par couches, dans cet ordre :

1. **Fonctionnement du conseil syndical** : bâtiments, lots et tantièmes, personnes, incidents et suivi des demandes au syndic, documents, agenda, échéances réglementaires.
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
COPRONOME_DEBUG=1 .venv/bin/python manage.py runserver
```

En production, la configuration se lit dans les variables `COPRONOME_*` (modèle : `.env.example`).

## Contribuer : aucun secret, aucune donnée réelle

Avant le premier commit, dans votre clone :

```bash
git config core.hooksPath .githooks   # active le contrôle avant commit
```

Le hook refuse un commit qui contient un secret, un IBAN, un numéro de téléphone ou une adresse mail hors domaines fictifs (`.gitleaks.toml`, avec [gitleaks](https://github.com/gitleaks/gitleaks) installé). Il vérifie aussi les termes privés de votre copropriété (nom, adresse, noms des personnes), listés un par ligne **hors du dépôt**, dans `~/.config/copronome/termes-prives.txt`. La CI rejoue le même scan sur chaque PR.

## Licence

[AGPL-3.0](LICENSE) : si vous proposez une version modifiée de Copronome en service à d'autres personnes, vous devez en publier le code source.

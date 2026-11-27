# Copronome — instructions pour les outils IA

> À lire en premier. Dépôt **public** (AGPL-3.0), logiciel libre de gestion de copropriété. Conception et décisions : ADR `2026-11-27-conception-et-stack-app-copro` et `2026-11-26-hebergement-app-copro-vps-ovh`, dans le dépôt privé `knowledge-base` (KB = source de vérité pour l'infrastructure et les décisions ; ce dépôt porte le code et sa doc).

## Règles non négociables

1. **Aucune donnée réelle** dans le code, les fixtures, les tests, les commits ou les PR : ni nom ou adresse de la copropriété, ni nom de copropriétaire, ni IBAN, téléphone ou mail réel. Données de démonstration **fictives** uniquement (domaines `example.org`, téléphones en `00 00 00 00`, IBAN fictif de `.gitleaks.toml`).
2. **Aucun secret** dans le dépôt : configuration par variables `COPRONOME_*` (`.env.example` pour les noms, `.env` jamais versionné). Le hook pre-commit (gitleaks + termes privés hors dépôt) et la CI le vérifient ; un refus ne se contourne pas (`--no-verify` interdit), il se corrige.
3. **Pas de force-push**, jamais. `main` est protégée par un ruleset (PR obligatoire, checks requis, aucun contournement).
4. **Identité git noreply** : `Jqh63 <12471916+Jqh63@users.noreply.github.com>`.
5. **Ne pas modifier `CLAUDE.md` sans demande explicite** de Yann.

## Workflow

- Toute modification passe par une **branche éphémère + PR** : `<type>/<sujet-court>` depuis `origin/main`, jamais de push direct sur `main`.
- Commits en **conventional commits français, à l'impératif**, sans scope (`feat: ajouter les lots`), sujet < 72 caractères, sans point final. Merge sans squash.
- **`-R Jqh63/copronome` sur toute commande `gh pr` / `gh issue`** : plusieurs clones partagent le sandbox et les numéros de PR se recoupent entre dépôts.
- Interface, messages et noms du domaine métier **en français** (`Lot`, `Batiment`, `Detention`) ; noms techniques génériques en anglais acceptés.

## Commandes

```bash
python3 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt -r requirements-dev.txt
git config core.hooksPath .githooks       # une fois par clone
.venv/bin/pytest -q                        # tests (SQLite ; la CI rejoue sur Postgres)
.venv/bin/ruff check . && .venv/bin/ruff format --check .
COPRONOME_DEBUG=1 .venv/bin/python manage.py runserver
```

Dépendances : éditer `requirements*.in`, puis `pip-compile --generate-hashes --allow-unsafe <fichier>.in`. Django reste sur la **branche LTS** (5.2 jusqu'au 2028-04-30).

## Principes de code

- **Une instance = une copropriété** : aucun filtre `copro_id`, rien de propre à une copropriété dans le code.
- **Contrôle d'accès centralisé** : une seule fonction décide (rôle, périmètre, objet) ; toute vue l'appelle, et le banc rôle × vue échoue sinon.
- **Journaux en ajout seul** (incidents, audit) : pas de modification ni de suppression d'un événement.
- Gabarits autoéchappés, **CSP stricte** (aucun script ni style inline), htmx sans `hx-on`.
- Discipline d'édition : 1 commit = 1 changement logique ; pas d'auto-fix hors sujet (signaler, proposer) ; pas de fonctionnalité spéculative ; explicite plutôt qu'élégant.
- Une règle juridique (majorités, délais, fréquences de contrôle) n'entre dans le code qu'**avec sa source** (article, texte) en commentaire ou en doc.

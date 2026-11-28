# Licences des dépendances

> Dernière mise à jour : 2026-11-28
> Statut : stable

Inventaire de ce que l'image de Copronome embarque, tenu à jour avec `requirements.txt` (le banc `tests/test_licences.py` échoue si un paquet épinglé manque ici). Il sert à vérifier la compatibilité avec l'AGPL-3.0 et à préparer toute double licence ou cession (ADR domaine et instances, § 11). Relevé sur les métadonnées des paquets installés (`License-Expression`, fichiers de licence du paquet) ; **ce n'est pas une analyse juridique**.

## Paquets Python de l'image (`requirements.txt`)

| Paquet | Version | Licence | Remarque |
|---|---|---|---|
| asgiref | 3.13.0 | BSD-3-Clause | |
| cffi | 2.1.1 | MIT-0 | |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | au choix |
| django | 5.2.19 | BSD-3-Clause | |
| django-allauth | 65.23.0 | MIT | |
| fido2 | 2.2.1 | BSD-2-Clause | `fido2/hid/*` sous Apache-2.0, `public_suffix_list.dat` sous MPL-2.0 (fichiers du paquet) |
| gunicorn | 27.0.1 | MIT | relevé sur PyPI (absent du venv de développement) |
| psycopg | 3.3.9 | LGPL-3.0-only | bibliothèque utilisée sans modification |
| psycopg-binary | 3.3.9 | LGPL-3.0-only | embarque libpq et ses bibliothèques (OpenSSL, Kerberos, OpenLDAP, Cyrus SASL), chacune sous sa licence : **à inventorier** avant une vente |
| pycparser | 3.12 | BSD-3-Clause | |
| qrcode | 8.2 | BSD (texte du paquet) | classificateur PyPI « Other/Proprietary License » aussi déclaré : **à vérifier** |
| sqlparse | 0.6.1 | BSD-3-Clause | |
| typing-extensions | 4.16.0 | PSF-2.0 | |
| whitenoise | 6.12.0 | MIT | |

## Images Docker

| Image | Rôle | Licence |
|---|---|---|
| `python:3.12-slim-trixie` | base de l'image de l'app | Python (PSF-2.0) sur Debian (paquets sous leurs licences propres) |
| `postgres:17-alpine` | base de données | PostgreSQL License |
| `caddy:2-alpine` | proxy TLS | Apache-2.0 |

Les images tierces ne sont pas redistribuées par ce dépôt : `compose.yaml` les tire de Docker Hub.

## Outils de développement

`requirements-dev.txt` (pytest, ruff, playwright, pip-audit…) ne part pas dans l'image : hors inventaire.

## Lecture

- Aucune dépendance sous GPL ou AGPL : toutes sont permissives (BSD, MIT, Apache, PSF) ou à copyleft faible (LGPL, MPL), compatibles avec la distribution de Copronome sous AGPL-3.0.
- Une licence non libre du code de Copronome (double licence, cession) resterait possible côté dépendances, à condition de respecter leurs avis de copyright et, pour psycopg (LGPL) et le fichier MPL de fido2, de redistribuer leur source inchangée ou modifiée. À faire confirmer avant toute vente.
- Ajouter une dépendance : l'ajouter ici dans la même PR que `requirements.txt`.

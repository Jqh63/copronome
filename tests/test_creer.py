"""Création idempotente des instances (exploitation/creer.py), contrat § 3 de l'ADR."""

import stat
from pathlib import Path

from exploitation import creer as c
from exploitation import registre as r

EXEMPLE = Path(__file__).resolve().parent.parent / "exploitation" / "registre.exemple.toml"
ACTIVE = "i3f9a0c1d2e4b"


def reg(slug="les-tilleuls-clermont", anciens=()):
    inst = {"id": ACTIVE, "slug": slug, "nom": "Les Tilleuls", "commune": "Clermont-Ferrand"}
    inst |= {"etat": "active", "anciens_slugs": list(anciens)}
    return r.valider({"version": 1, "domaine": "copro.example.org", "instance": [inst]})


def env(racine):
    return c.lire_env(racine / ACTIVE / "instance.env")


def test_creation_puis_rejeu_inchange(tmp_path):
    registre = reg()
    assert c.creer(registre, registre.instances[0], tmp_path) == "créée"
    premier = env(tmp_path)
    assert premier["COPRONOME_DOMAINE"] == "les-tilleuls-clermont.copro.example.org"
    assert premier["COPRONOME_URL_PUBLIQUE"] == "https://les-tilleuls-clermont.copro.example.org"
    assert premier["COPRONOME_DB_NAME"] == premier["COPRONOME_DB_OWNER"] == f"copronome_{ACTIVE}"
    assert premier["COPRONOME_DB_APP_USER"] == f"copronome_{ACTIVE}_app"
    assert all(len(premier[s]) >= 50 for s in c.SECRETS)
    assert len({premier[s] for s in c.SECRETS}) == 3

    fichier = tmp_path / ACTIVE / "instance.env"
    avant = fichier.read_bytes()
    assert c.creer(registre, registre.instances[0], tmp_path) == "inchangée"
    assert fichier.read_bytes() == avant


def test_droits_restreints(tmp_path):
    registre = reg()
    c.creer(registre, registre.instances[0], tmp_path)
    assert stat.S_IMODE((tmp_path / ACTIVE / "instance.env").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / ACTIVE).stat().st_mode) & 0o077 == 0


def test_renommage_recale_l_adresse_sans_toucher_aux_secrets(tmp_path):
    avant = reg()
    c.creer(avant, avant.instances[0], tmp_path)
    secrets_avant = {s: env(tmp_path)[s] for s in c.SECRETS}
    apres = reg(slug="tilleuls-clermont", anciens=["les-tilleuls-clermont"])
    assert c.creer(apres, apres.instances[0], tmp_path) == "mise à jour"
    valeurs = env(tmp_path)
    assert valeurs["COPRONOME_DOMAINE"] == "tilleuls-clermont.copro.example.org"
    assert {s: valeurs[s] for s in c.SECRETS} == secrets_avant
    assert valeurs["COPRONOME_DB_NAME"] == f"copronome_{ACTIVE}"


def test_variable_ajoutee_a_la_main_conservee(tmp_path):
    registre = reg()
    c.creer(registre, registre.instances[0], tmp_path)
    fichier = tmp_path / ACTIVE / "instance.env"
    fichier.write_text(fichier.read_text() + "COPRONOME_EMAIL_HOST=smtp.example.org\n")
    assert c.creer(registre, registre.instances[0], tmp_path) == "inchangée"
    assert env(tmp_path)["COPRONOME_EMAIL_HOST"] == "smtp.example.org"


def test_secret_vide_regenere(tmp_path):
    registre = reg()
    c.creer(registre, registre.instances[0], tmp_path)
    fichier = tmp_path / ACTIVE / "instance.env"
    fichier.write_text(fichier.read_text().replace("COPRONOME_SECRET_KEY=", "COPRONOME_SECRET_KEY=\n#", 1))
    assert c.creer(registre, registre.instances[0], tmp_path) == "mise à jour"
    assert len(env(tmp_path)["COPRONOME_SECRET_KEY"]) >= 50


def test_cli(tmp_path, capsys):
    assert c.main([str(EXEMPLE), str(tmp_path)]) == 0
    assert f"{ACTIVE} (les-tilleuls-clermont) : créée" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == [ACTIVE]  # l'instance supprimée n'est pas créée
    assert c.main([str(EXEMPLE), str(tmp_path)]) == 0
    assert "inchangée" in capsys.readouterr().out
    assert c.main([str(EXEMPLE), str(tmp_path), "i7b20e5f61a08"]) == 1
    assert "supprimee, rien créé" in capsys.readouterr().err
    assert c.main([str(EXEMPLE), str(tmp_path), "iinconnue00"]) == 1
    assert c.main([str(EXEMPLE), str(tmp_path / "absente")]) == 1
    assert c.main([]) == 2

"""Restauration d'une sauvegarde chiffrée (exploitation/restaurer.py), ADR § 9.

`docker` et `age` sont remplacés par des faux dans le PATH : ce banc prouve
l'enchaînement (vérifications avant écriture, ordre, codes de retour). Le vrai
déchiffrement et la vraie restauration sont joués par docker/essai-conteneurs.sh."""

import json
import os
import sys

import pytest

from exploitation import restaurer as r
from exploitation import sauvegarder as s

IID = "i3f9a0c1d2e4b"
FAUX_DOCKER = """#!{py}
import os, sys
a = sys.argv[1:]
journal = os.environ["FAUX_JOURNAL"]
open(journal, "a").write(" ".join(a) + "\\n")
echec = os.environ.get("FAUX_ECHEC", "")
if a[:2] == ["volume", "inspect"]:
    sys.exit(1 if echec == "volume" else 0)
if a[0] == "inspect":
    print("sha256:image-du-cluster"); sys.exit(0)
if "psql" in a:
    print(os.environ.get("FAUX_TABLES", "0")); sys.exit(0)
if "pg_restore" in a or a[-1] == "-":
    recu = sys.stdin.buffer.read()
    nom = "pg_restore" if "pg_restore" in a else "tar"
    open(journal + "." + nom, "wb").write(recu)
    if echec == nom:
        sys.stderr.write(nom + ": erreur de restauration\\n"); sys.exit(1)
    sys.exit(0)
if a[0] == "run" and "sh" in a:
    sys.exit(1 if echec == "volume-plein" else 0)
sys.exit(3)
"""
FAUX_AGE = """#!{py}
import os, sys
a = sys.argv[1:]
assert a[:2] == ["-d", "-i"], a
if os.environ.get("FAUX_ECHEC") == "age":
    sys.stderr.write("age: no identity matched\\n"); sys.exit(1)
sys.stdout.buffer.write(open(a[3], "rb").read().removeprefix(b"AGE:"))
"""


@pytest.fixture
def faux(tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for nom, code in (("docker", FAUX_DOCKER), ("age", FAUX_AGE)):
        (bin_ / nom).write_text(code.format(py=sys.executable))
        (bin_ / nom).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAUX_JOURNAL", str(tmp_path / "journal"))
    monkeypatch.delenv("FAUX_ECHEC", raising=False)
    monkeypatch.delenv("FAUX_TABLES", raising=False)
    (tmp_path / "cle").write_text("AGE-SECRET-KEY-1FAUSSE\n")
    sauvegarde = tmp_path / "sauvegarde"
    sauvegarde.mkdir()
    (sauvegarde / "base.dump.age").write_bytes(b"AGE:PGDMP")
    (sauvegarde / "fichiers.tar.age").write_bytes(b"AGE:TAR")
    manifeste = {
        "format": s.FORMAT,
        "instance": IID,
        "horodatage": "20261128T030000Z",
        "parties": {nom: {"sha256": s.empreinte(sauvegarde / nom)} for nom in s.PARTIES},
    }
    (sauvegarde / "MANIFESTE").write_text(json.dumps(manifeste))
    return tmp_path


def env(**autres):
    return {
        "COPRONOME_INSTANCE_ID": IID,
        "COPRONOME_DB_NAME": f"copronome_{IID}",
        "COPRONOME_DB_OWNER": f"copronome_{IID}_proprietaire",
    } | autres


def journal(faux):
    chemin = faux / "journal"
    return chemin.read_text() if chemin.exists() else ""


def restaurer(faux, **kw):
    return r.restaurer(faux / "sauvegarde", faux / "cle", env(), **kw)


def test_restauration_complete(faux):
    assert restaurer(faux)["instance"] == IID
    assert (faux / "journal.pg_restore").read_bytes() == b"PGDMP"
    assert (faux / "journal.tar").read_bytes() == b"TAR"
    lignes = journal(faux).splitlines()
    restore = next(i for i, ligne in enumerate(lignes) if "pg_restore" in ligne)
    tar = next(i for i, ligne in enumerate(lignes) if ligne.endswith("-xpf -"))
    assert restore < tar, "base avant fichiers"
    assert f"--role=copronome_{IID}_proprietaire --exit-on-error -d copronome_{IID}" in lignes[restore]
    assert "--no-owner --no-acl" in lignes[restore]
    assert f"--network none --entrypoint tar -v copronome-{IID}_media:/fichiers " in lignes[tar]
    assert "sha256:image-du-cluster -C /fichiers -xpf -" in lignes[tar]


def test_projet_nomme_le_volume(faux):
    restaurer(faux, projet="copronome-essai-x")
    assert "copronome-essai-x_media:/fichiers" in journal(faux)


@pytest.mark.parametrize(
    ("alterer", "message"),
    [
        (lambda d: (d / "base.dump.age").write_bytes(b"AGE:AUTRE"), "base.dump.age absent ou altéré"),
        (lambda d: (d / "fichiers.tar.age").unlink(), "fichiers.tar.age absent ou altéré"),
        (lambda d: (d / "MANIFESTE").write_text("{"), "manifeste illisible"),
        (lambda d: (d / "MANIFESTE").write_text('{"format": 2}'), "format 2 inconnu"),
    ],
)
def test_manifeste_verifie_avant_tout(faux, alterer, message):
    alterer(faux / "sauvegarde")
    with pytest.raises(r.EchecRestauration, match=message):
        restaurer(faux)
    assert journal(faux) == "", "aucun appel docker avant la vérification"


@pytest.mark.parametrize(
    ("echec", "tables", "message"),
    [
        ("", "3", "non vide : rien restauré"),
        ("volume", "0", "introuvable"),
        ("volume-plein", "0", "non vide : rien restauré"),
    ],
)
def test_cible_non_vide_ou_absente_refusee(faux, monkeypatch, echec, tables, message):
    monkeypatch.setenv("FAUX_ECHEC", echec)
    monkeypatch.setenv("FAUX_TABLES", tables)
    with pytest.raises(r.EchecRestauration, match=message):
        restaurer(faux)
    assert "pg_restore" not in journal(faux) and "-xpf" not in journal(faux)


@pytest.mark.parametrize(
    ("echec", "message", "tar_joue"),
    [
        ("age", "age : code 1 : age: no identity matched", False),
        ("pg_restore", "pg_restore : code 1", False),
        ("tar", "tar : code 1", True),
    ],
)
def test_echec_du_dechiffrement_ou_du_consommateur(faux, monkeypatch, echec, message, tar_joue):
    monkeypatch.setenv("FAUX_ECHEC", echec)
    with pytest.raises(r.EchecRestauration, match=message):
        restaurer(faux)
    assert ("-xpf" in journal(faux)) is tar_joue


def test_env_et_cle_obligatoires(faux):
    with pytest.raises(r.EchecRestauration, match="COPRONOME_DB_OWNER"):
        r.restaurer(faux / "sauvegarde", faux / "cle", env(COPRONOME_DB_OWNER=""))
    with pytest.raises(r.EchecRestauration, match="clé .* absente"):
        r.restaurer(faux / "sauvegarde", faux / "absente", env())


def test_main(faux, capsys, monkeypatch):
    fichier = faux / "instance.env"
    fichier.write_text("".join(f"{k}={v}\n" for k, v in env().items()))
    args = [str(faux / "sauvegarde"), str(faux / "cle"), str(fichier)]
    assert r.main(args) == 0
    assert f"sauvegarde {IID} du 20261128T030000Z restaurée" in capsys.readouterr().out
    assert r.main(args[:2]) == 2
    assert r.main([*args, "--projet"]) == 2
    monkeypatch.setenv("FAUX_TABLES", "1")
    assert r.main([*args, "--projet", "copronome-essai-x"]) == 1
    assert "ECHEC" in capsys.readouterr().err

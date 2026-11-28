"""Sauvegarde chiffrée d'une instance (exploitation/sauvegarder.py), ADR § 9.

`docker` et `age` sont remplacés par des faux dans le PATH : ce banc prouve
l'enchaînement (codes de retour, dossier partiel, manifeste, rétention). Le
vrai chiffrement et la vraie restauration sont joués par docker/essai-conteneurs.sh."""

import datetime as dt
import hashlib
import json
import os
import stat
import sys

import pytest

from exploitation import sauvegarder as s

IID = "i3f9a0c1d2e4b"
CLE = "age1" + "q" * 58
FAUX_DOCKER = """#!{py}
import os, sys
a = sys.argv[1:]
open(os.environ["FAUX_JOURNAL"], "a").write(" ".join(a) + "\\n")
echec = os.environ.get("FAUX_ECHEC", "")
if a[:2] == ["volume", "inspect"]:
    sys.exit(1 if echec == "volume" else 0)
if a[0] == "inspect":
    print("sha256:image-du-cluster"); sys.exit(0)
if "pg_dump" in a:
    if echec == "pg_dump":
        sys.stderr.write("pg_dump: connexion refusée\\n"); sys.exit(1)
    if echec == "age":
        # Plus gros que le tampon du tube : age, sorti sans lire, casse le
        # tube et le producteur meurt (BrokenPipe) — l'ordre réel de l'échec.
        sys.stdout.write("D" * 1_000_000); sys.exit(0)
    sys.stdout.write("DUMP"); sys.exit(0)
if a[0] == "run":
    sys.stdout.write("TAR"); sys.exit(0)
sys.exit(3)
"""
FAUX_AGE = """#!{py}
import os, sys
a = sys.argv[1:]
if os.environ.get("FAUX_ECHEC") == "age":
    sys.stderr.write("age: destinataire invalide\\n"); sys.exit(1)
assert a[0] == "-r" and a[2] == "-o", a
open(a[3], "wb").write(b"AGE[" + a[1].encode() + b"]" + sys.stdin.buffer.read())
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
    return tmp_path


def env(**autres):
    base = {
        "COPRONOME_INSTANCE_ID": IID,
        "COPRONOME_DB_NAME": f"copronome_{IID}",
        "COPRONOME_SAUVEGARDE_DESTINATAIRE": CLE,
    }
    return base | autres


def date(jour):
    return dt.datetime(2026, 11, jour, 3, 0, 0, tzinfo=dt.UTC)


def test_sauvegarde_chiffree_complete(faux):
    final = s.sauvegarder(env(), faux / "dest", maintenant=date(28))
    assert final == faux / "dest" / IID / "20261128T030000Z"
    assert (final / "base.dump.age").read_bytes() == f"AGE[{CLE}]DUMP".encode()
    assert (final / "fichiers.tar.age").read_bytes() == f"AGE[{CLE}]TAR".encode()
    manifeste = json.loads((final / "MANIFESTE").read_text())
    assert manifeste["instance"] == IID and manifeste["format"] == 1
    for nom in s.PARTIES:
        contenu = (final / nom).read_bytes()
        assert manifeste["parties"][nom] == {
            "octets": len(contenu),
            "sha256": hashlib.sha256(contenu).hexdigest(),
        }
    assert stat.S_IMODE(final.stat().st_mode) == 0o700
    journal = (faux / "journal").read_text()
    assert f"exec -u postgres copronome-postgres pg_dump -Fc -d copronome_{IID}" in journal
    # Volume en lecture seule, conteneur sans réseau, image du cluster.
    assert f"--network none --read-only --entrypoint tar -v copronome-{IID}_media:/fichiers:ro" in journal
    assert "sha256:image-du-cluster -C /fichiers -cf - ." in journal


def test_projet_nomme_le_volume(faux):
    s.sauvegarder(env(), faux / "dest", projet="copronome-essai-x", maintenant=date(28))
    assert "copronome-essai-x_media:/fichiers:ro" in (faux / "journal").read_text()


@pytest.mark.parametrize(
    ("echec", "message"),
    [("pg_dump", "connexion refusée"), ("age", "destinataire"), ("volume", "introuvable")],
)
def test_echec_ne_laisse_rien(faux, monkeypatch, echec, message):
    monkeypatch.setenv("FAUX_ECHEC", echec)
    with pytest.raises(s.EchecSauvegarde, match=message):
        s.sauvegarder(env(), faux / "dest", maintenant=date(28))
    assert list((faux / "dest" / IID).iterdir()) == []


@pytest.mark.parametrize("cle", ["", "age1court", "AGE-SECRET-KEY-1" + "Q" * 58])
def test_destinataire_obligatoire_et_public(faux, cle):
    with pytest.raises(s.EchecSauvegarde, match="DESTINATAIRE"):
        s.sauvegarder(env(COPRONOME_SAUVEGARDE_DESTINATAIRE=cle), faux / "dest")


def test_partiel_ancien_ignore_et_elagage(faux):
    dossier = faux / "dest" / IID
    for jour in (24, 25, 26, 27):
        s.sauvegarder(env(), faux / "dest", maintenant=date(jour))
    (dossier / "20261123T030000Z.partiel").mkdir()
    retirees = s.elaguer(dossier, 2)
    assert [p.name for p in retirees] == ["20261124T030000Z", "20261125T030000Z"]
    assert sorted(p.name for p in dossier.iterdir()) == [
        "20261123T030000Z.partiel",
        "20261126T030000Z",
        "20261127T030000Z",
    ]
    with pytest.raises(ValueError):
        s.elaguer(dossier, 0)


def test_main(faux, capsys):
    fichier = faux / "instance.env"
    fichier.write_text("".join(f"{k}={v}\n" for k, v in env().items()))
    assert s.main([str(fichier), str(faux / "dest"), "--garder", "3"]) == 0
    assert "écrite" in capsys.readouterr().out
    assert s.main([str(fichier)]) == 2
    assert s.main([str(fichier), str(faux / "dest"), "--garder", "0"]) == 2
    fichier.write_text(f"COPRONOME_INSTANCE_ID={IID}\n")
    assert s.main([str(fichier), str(faux / "dest")]) == 1
    assert "ECHEC" in capsys.readouterr().err

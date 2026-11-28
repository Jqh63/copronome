"""Frontal Caddy généré depuis le registre (exploitation/frontal.py), ADR § 2."""

from pathlib import Path

from copronome.journal import PREFIXES_A_JETON
from exploitation import frontal as f
from exploitation import registre as r

EXEMPLE = Path(__file__).resolve().parent.parent / "exploitation" / "registre.exemple.toml"


def reg(*instances):
    return r.valider({"version": 1, "domaine": "copro.example.org", "instance": list(instances)})


def inst(iid, slug, etat="active", anciens=()):
    return {"id": iid, "slug": slug, "nom": "N", "commune": "C", "etat": etat, "anciens_slugs": list(anciens)}


def blocs(conf):
    """Blocs de site : en-tête de bloc → contenu, hors options globales et extraits."""
    sortie, cle = {}, None
    for ligne in conf.splitlines():
        if ligne.endswith("{") and not ligne.startswith(("\t", "{", "(")):
            cle = ligne[:-1].strip()
            sortie[cle] = []
        elif ligne == "}":
            cle = None
        elif cle:
            sortie[cle].append(ligne.strip())
    return sortie


def test_un_bloc_par_etat():
    conf = f.generer(
        reg(
            inst("iaaaa00000001", "active-vichy", anciens=["ancien-vichy"]),
            inst("iaaaa00000002", "en-pause-vichy", etat="suspendue"),
            inst("iaaaa00000003", "partie-vichy", etat="supprimee", anciens=["tres-ancien-vichy"]),
        )
    )
    b = blocs(conf)
    assert b["active-vichy.copro.example.org"] == ["import instance copronome-iaaaa00000001"]
    assert b["ancien-vichy.copro.example.org"] == ["redir https://active-vichy.copro.example.org{uri} 308"]
    assert b["en-pause-vichy.copro.example.org"] == ['respond "Instance suspendue" 503']
    assert b["http://"] == ["abort"]
    # Une instance supprimée n'est plus servie, ni par son slug ni par ses anciens.
    assert "partie-vichy" not in conf and "tres-ancien-vichy" not in conf


def test_aucune_instance_seulement_le_refus():
    assert list(blocs(f.generer(reg()))) == ["http://"]


def test_tls_interne_en_option():
    assert "local_certs" not in f.generer(reg())
    assert "\tlocal_certs\n" in f.generer(reg(), tls_interne=True)


def test_options_de_securite():
    conf = f.generer(reg(inst("iaaaa00000001", "a-vichy")))
    assert "strict_sni_host on" in conf
    assert "admin localhost:2019" in conf
    assert "{$COPRONOME_CORPS_MAX_MO:21}MiB" in conf
    assert "reverse_proxy {args[0]}:8000" in conf


def test_journal_masque_les_memes_prefixes_que_django():
    conf = f.generer(reg())
    ligne = next(x for x in conf.splitlines() if "request>uri regexp" in x)
    assert "^/(" + "|".join(PREFIXES_A_JETON) + ")/[^?]* /${1}/[jeton]" in ligne
    for entete in ("Referer", "Cookie", "Authorization"):
        assert f"request>headers>{entete} delete" in conf
    assert "resp_headers>Set-Cookie delete" in conf


def test_ecriture_seulement_si_change(tmp_path):
    sortie = tmp_path / "Caddyfile"
    assert f.ecrire(sortie, "a") is True
    inode = sortie.stat().st_ino
    assert f.ecrire(sortie, "a") is False
    assert sortie.stat().st_ino == inode
    assert f.ecrire(sortie, "b") is True
    assert sortie.read_text() == "b"


def test_cli(tmp_path, capsys):
    sortie = tmp_path / "Caddyfile"
    assert f.main([str(EXEMPLE), str(sortie), "--tls-interne"]) == 0
    assert "écrit (1 instance(s) active(s))" in capsys.readouterr().out
    assert "les-tilleuls-clermont.copro.example.org {" in sortie.read_text()
    assert f.main([str(EXEMPLE), str(sortie), "--tls-interne"]) == 0
    assert "inchangé" in capsys.readouterr().out
    assert f.main([str(EXEMPLE), str(tmp_path / "absent" / "Caddyfile")]) == 1
    assert f.main([str(EXEMPLE), str(sortie), "--autre"]) == 2
    assert f.main([str(EXEMPLE)]) == 2

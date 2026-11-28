"""Registre des instances (exploitation/registre.py) : invariants du § 4 de l'ADR."""

from pathlib import Path

import pytest

from exploitation import registre as r

EXEMPLE = Path(__file__).resolve().parent.parent / "exploitation" / "registre.exemple.toml"


def instance(**champs):
    base = {"id": "iaaaa0000bbbb", "slug": "les-tilleuls-vichy", "nom": "Les Tilleuls", "commune": "Vichy"}
    base["etat"] = "active"
    return base | champs


def donnees(*instances, **racine):
    return {"version": 1, "domaine": "copro.example.org", "instance": list(instances)} | racine


def erreurs(d):
    with pytest.raises(r.RegistreInvalide) as e:
        r.valider(d)
    return e.value.erreurs


def test_exemple_versionne_valide():
    reg = r.charger(EXEMPLE)
    assert reg.domaine == "copro.example.org"
    assert [i.etat for i in reg.instances] == ["active", "supprimee"]
    assert [i.slug for i in reg.actives()] == ["les-tilleuls-clermont"]


def test_registre_vide_admis():
    assert r.valider(donnees()).instances == ()


def test_identifiant_en_double_refuse():
    e = erreurs(donnees(instance(), instance(slug="autre-vichy")))
    assert any("identifiant déjà pris" in x for x in e)


def test_slug_jamais_reattribue_meme_supprime_ou_ancien():
    supprimee = instance(etat="supprimee")
    assert any("jamais réattribué" in x for x in erreurs(donnees(supprimee, instance(id="icccc1111dddd"))))
    renommee = instance(slug="tilleuls-vichy", anciens_slugs=["les-tilleuls-vichy"])
    assert any("jamais réattribué" in x for x in erreurs(donnees(renommee, instance(id="icccc1111dddd"))))


@pytest.mark.parametrize("slug", ["www", "admin", "api", "portail", "mail", "acme"])
def test_slug_reserve_refuse(slug):
    assert any("réservé" in x for x in erreurs(donnees(instance(slug=slug))))


@pytest.mark.parametrize(
    "slug", ["", "Tilleuls", "-tilleuls", "tilleuls-", "les--tilleuls", "les_tilleuls", "é", "a" * 64, 3]
)
def test_slug_hors_label_dns_refuse(slug):
    assert any("invalide" in x for x in erreurs(donnees(instance(slug=slug))))


@pytest.mark.parametrize("iid", ["", "1abcdefgh", "iABCDEFGH", "i-abcdefg", "icourt", "i" + "a" * 32, None])
def test_identifiant_invalide_refuse(iid):
    assert any("identifiant" in x for x in erreurs(donnees(instance(id=iid))))


def test_cle_inconnue_refusee():
    assert any("clé inconnue 'comune'" in x for x in erreurs(donnees(instance(comune="Vichy"))))
    assert any("clé inconnue 'domain'" in x for x in erreurs(donnees(domain="x.org")))


def test_champs_obligatoires_et_etat():
    e = erreurs(donnees(instance(nom=" ", etat="archivee") | {"commune": None}))
    assert any("`nom`" in x for x in e)
    assert any("`commune`" in x for x in e)
    assert any("état 'archivee'" in x for x in e)


def test_version_et_domaine():
    e = erreurs(donnees(version=2, domaine="localhost"))
    assert any("version 2" in x for x in e)
    assert any("domaine 'localhost'" in x for x in e)


def test_toutes_les_erreurs_d_un_coup():
    assert len(erreurs(donnees(instance(slug="www", etat="x"), version=0))) == 3


def test_nouvel_id_conforme_et_aleatoire():
    ids = {r.nouvel_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(r.ID_RE.match(i) for i in ids)
    # Le nom Postgres le plus long dérivé de l'identifiant tient dans 63 octets.
    assert len("copronome_" + "i" + "a" * 31 + "_app") <= 63


def test_cli_verifier(tmp_path, capsys):
    assert r.main(["verifier", str(EXEMPLE)]) == 0
    assert "2 instance(s), dont 1 active(s)" in capsys.readouterr().out
    casse = tmp_path / "registre.toml"
    casse.write_text('version = 1\ndomaine = "copro.example.org"\n[[instance]]\nid = "x"\n')
    assert r.main(["verifier", str(casse)]) == 1
    assert "identifiant 'x' invalide" in capsys.readouterr().err
    casse.write_text("version = = 1\n")
    assert r.main(["verifier", str(casse)]) == 1
    assert "TOML illisible" in capsys.readouterr().err
    assert r.main(["verifier", str(tmp_path / "absent.toml")]) == 1
    assert r.main([]) == 2

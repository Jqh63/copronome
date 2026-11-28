"""Cluster Postgres partagé (exploitation/postgres.py), ADR domaine et instances § 2.

Le SQL est rejoué contre un vrai Postgres par docker/essai-conteneurs.sh (CI)."""

import stat

import pytest

from exploitation import creer as c
from exploitation import postgres as p
from exploitation import registre as r

A, B, C = "i3f9a0c1d2e4b", "i7b20e5f61a08", "i0c0ffee0000a"


def reg():
    instances = [
        {"id": A, "slug": "tilleuls", "nom": "N", "commune": "C", "etat": "active"},
        {"id": B, "slug": "parc", "nom": "N", "commune": "C", "etat": "suspendue"},
        {"id": C, "slug": "ancienne", "nom": "N", "commune": "C", "etat": "supprimee"},
    ]
    return r.valider({"version": 1, "domaine": "copro.example.org", "instance": instances})


def regles(conf):
    return [ligne.split("\t") for ligne in conf.splitlines() if ligne and not ligne.startswith("#")]


def test_pg_hba_une_ligne_par_instance_et_rien_d_autre():
    lignes = regles(p.pg_hba(reg()))
    assert lignes[0] == ["local", "all", "postgres", "peer"]
    assert ["host", f"copronome_{A}", f"copronome_{A},copronome_{A}_app", "all", "scram-sha-256"] in lignes
    # Suspendue : base gardée, l'app peut encore s'y connecter ; supprimée : plus rien.
    assert ["host", f"copronome_{B}", f"copronome_{B},copronome_{B}_app", "all", "scram-sha-256"] in lignes
    assert not any(C in "".join(ligne) for ligne in lignes)
    assert lignes[-1] == ["host", "all", "all", "all", "reject"]
    # Le superutilisateur n'a aucune ligne réseau autorisée.
    reseau = [ligne for ligne in lignes if ligne[0] == "host" and ligne[-1] != "reject"]
    assert not any("postgres" in ligne[2].split(",") for ligne in reseau)


def test_configurer_idempotent_et_secret_genere_une_fois(tmp_path):
    assert p.configurer(reg(), tmp_path) == ["pg_hba.conf", "postgres.env"]
    env = tmp_path / p.CLUSTER / "postgres.env"
    hba = tmp_path / p.CLUSTER / "conf" / "pg_hba.conf"
    mot_de_passe = c.lire_env(env)["COPRONOME_POSTGRES_PASSWORD"]
    assert len(mot_de_passe) >= 50
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / p.CLUSTER).stat().st_mode) == 0o700
    assert stat.S_IMODE(hba.stat().st_mode) == 0o644

    assert p.configurer(reg(), tmp_path) == []
    assert c.lire_env(env)["COPRONOME_POSTGRES_PASSWORD"] == mot_de_passe

    vide = r.valider({"version": 1, "domaine": "copro.example.org", "instance": []})
    assert p.configurer(vide, tmp_path) == ["pg_hba.conf"]
    assert A not in hba.read_text()
    assert c.lire_env(env)["COPRONOME_POSTGRES_PASSWORD"] == mot_de_passe


def env_instance(tmp_path):
    registre = reg()
    c.creer(registre, registre.instances[0], tmp_path)
    return c.lire_env(tmp_path / A / "instance.env")


def test_sql_cree_les_deux_roles_et_la_base(tmp_path):
    env = env_instance(tmp_path)
    requete = p.sql(env)
    base, app = f"copronome_{A}", f"copronome_{A}_app"
    assert requete.startswith("\\set ON_ERROR_STOP on\n")
    assert f'ALTER ROLE "{base}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE' in requete
    assert f'ALTER ROLE "{app}" LOGIN NOSUPERUSER' in requete
    assert f"PASSWORD '{env['COPRONOME_DB_PASSWORD']}'" in requete
    assert f"PASSWORD '{env['COPRONOME_DB_APP_PASSWORD']}'" in requete
    assert f'ALTER DATABASE "{base}" OWNER TO "{base}";' in requete
    assert f'REVOKE ALL ON DATABASE "{base}" FROM PUBLIC;' in requete
    assert f'GRANT CONNECT ON DATABASE "{base}" TO "{app}";' in requete
    # Création conditionnelle : rejouable sans erreur.
    assert requete.count("WHERE NOT EXISTS") == 3


def test_sql_echappe_les_valeurs(tmp_path):
    env = env_instance(tmp_path) | {"COPRONOME_DB_APP_PASSWORD": "a'b"}
    assert "PASSWORD 'a''b'" in p.sql(env)


@pytest.mark.parametrize(
    "changement",
    [
        {"COPRONOME_DB_APP_PASSWORD": ""},
        {"COPRONOME_DB_OWNER": "postgres"},
        {"COPRONOME_DB_APP_USER": f"copronome_{A}"},
        {"COPRONOME_DB_NAME": 'x"; DROP DATABASE y; --'},
    ],
)
def test_sql_refuse_un_env_incomplet_ou_dangereux(tmp_path, changement):
    with pytest.raises(ValueError):
        p.sql(env_instance(tmp_path) | changement)


def test_main(tmp_path, capsys):
    exemple = tmp_path / "registre.toml"
    exemple.write_text(
        f'version = 1\ndomaine = "copro.example.org"\n[[instance]]\nid = "{A}"\nslug = "tilleuls"\n'
        'nom = "N"\ncommune = "C"\netat = "active"\n',
        encoding="utf-8",
    )
    assert p.main(["configurer", str(exemple), str(tmp_path)]) == 0
    assert p.main(["configurer", str(exemple), str(tmp_path)]) == 0
    assert "inchangé" in capsys.readouterr().out
    assert c.main([str(exemple), str(tmp_path)]) == 0
    assert p.main(["sql", str(tmp_path / A / "instance.env")]) == 0
    assert "CREATE DATABASE" in capsys.readouterr().out
    assert p.main(["sql", str(tmp_path / "absent.env")]) == 1
    assert p.main(["autre"]) == 2

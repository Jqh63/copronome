"""Banc des droits (ADR, § 4) : toute route est contrôlée, chaque rôle voit
ce que la table prévoit, et un compte sans second facteur ne passe nulle part."""

from datetime import timedelta

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone

from acces.droits import ECRIRE, LIRE, peut
from acces.models import Affectation, Invitation, Role
from copro.models import Batiment, Lot

pytestmark = pytest.mark.django_db

# Modules de l'app : toute vue qui en vient doit être marquée par `exige` ou `public`.
MODULES_APP = ("copronome.", "copro.", "acces.", "incidents.", "documents.", "echeances.", "agenda.")


def _routes(resolver=None, prefixe=""):
    resolver = resolver or get_resolver()
    for motif in resolver.url_patterns:
        if isinstance(motif, URLResolver):
            yield from _routes(motif, prefixe + str(motif.pattern))
        elif isinstance(motif, URLPattern):
            yield prefixe + str(motif.pattern), motif.callback


def test_toute_vue_de_l_app_passe_par_le_controle_d_acces():
    non_marquees = [
        (route, vue.__module__)
        for route, vue in _routes()
        if vue.__module__.startswith(MODULES_APP) and not hasattr(vue, "controle_acces")
    ]
    assert non_marquees == []


def test_les_vues_publiques_sont_celles_attendues():
    publiques = sorted(
        route
        for route, vue in _routes()
        if vue.__module__.startswith(MODULES_APP) and getattr(vue, "controle_acces", None) == "public"
    )
    assert publiques == ["", "agenda/ical/<str:jeton>/", "invitation/<str:jeton>/", "sante/"]


def _compte(email, role=None, batiment=None, mfa=True):
    utilisateur = get_user_model().objects.create_user(username=email, email=email, password="x")
    if role:
        Affectation.objects.create(utilisateur=utilisateur, role=role, batiment=batiment)
    if mfa:
        Authenticator.objects.create(user=utilisateur, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utilisateur


@pytest.fixture
def demo():
    call_command("charger_demo")


# Lecture de la liste des lots, rôle par rôle (tableau de l'ADR).
ATTENDU_LOTS = {
    Role.ADMIN: 200,
    Role.PRESIDENT: 200,
    Role.MEMBRE_CS: 200,
    Role.CONTROLEUR: 403,
    Role.SYNDIC: 403,
    Role.COPROPRIETAIRE: 403,
}


@pytest.mark.parametrize("role", list(Role))
def test_matrice_role_lots(client, demo, role):
    assert set(ATTENDU_LOTS) == set(Role), "chaque rôle doit avoir son attendu"
    client.force_login(_compte(f"{role}@example.org", role))
    assert client.get(reverse("lots")).status_code == ATTENDU_LOTS[role]


def test_anonyme_redirige_vers_la_connexion(client, demo):
    reponse = client.get(reverse("lots"))
    assert reponse.status_code == 302
    assert reponse["Location"].startswith("/compte/login/")


def test_compte_sans_role_refuse(client, demo):
    client.force_login(_compte("sansrole@example.org"))
    assert client.get(reverse("lots")).status_code == 403


def test_perimetre_batiment_filtre_la_liste_et_l_objet(client, demo):
    bat_a = Batiment.objects.get(nom="Bâtiment A")
    membre = _compte("membre-a@example.org", Role.MEMBRE_CS, batiment=bat_a)
    client.force_login(membre)
    contenu = client.get(reverse("lots")).content.decode()
    assert "A01" in contenu and "B01" not in contenu
    assert peut(membre, LIRE, "structure", Lot.objects.get(numero="A01"))
    assert not peut(membre, LIRE, "structure", Lot.objects.get(numero="B01"))


def test_admin_technique_n_ecrit_pas_le_metier():
    admin = _compte("admin@example.org", Role.ADMIN)
    assert peut(admin, ECRIRE, "comptes")
    for domaine in ("structure", "personnes", "incidents", "documents"):
        assert not peut(admin, ECRIRE, domaine)


def test_droit_inconnu_leve_une_erreur():
    with pytest.raises(ValueError):
        peut(_compte("x@example.org", Role.PRESIDENT), LIRE, "domaine-inexistant")


# Second facteur obligatoire : chaque route de l'app, requêtes htmx comprises.
ROUTES_SANS_ARGUMENT = sorted(
    r for r, v in _routes() if v.__module__.startswith(MODULES_APP) and "<" not in r and r != "sante/"
)


@pytest.mark.parametrize("route", ROUTES_SANS_ARGUMENT)
@pytest.mark.parametrize("htmx", [False, True])
def test_compte_sans_second_facteur_bloque_partout(client, demo, route, htmx):
    client.force_login(_compte("president@example.org", Role.PRESIDENT, mfa=False))
    entetes = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    reponse = client.get("/" + route, **entetes)
    if htmx:
        assert reponse.status_code == 401
        assert reponse["HX-Redirect"] == reverse("mfa_index")
    else:
        assert reponse.status_code == 302
        assert reponse["Location"] == reverse("mfa_index")


def test_page_d_enrolement_accessible_sans_second_facteur(client):
    client.force_login(_compte("president@example.org", Role.PRESIDENT, mfa=False))
    assert client.get(reverse("mfa_index")).status_code == 200


def test_copropriétaire_sans_second_facteur_n_est_pas_force(client, demo):
    client.force_login(_compte("copro@example.org", Role.COPROPRIETAIRE, mfa=False))
    assert client.get(reverse("accueil")).status_code == 200


def test_admin_django_passe_par_la_connexion_allauth(client):
    reponse = client.get("/admin/login/")
    assert reponse.status_code == 302
    assert reponse["Location"].startswith("/compte/login/")


def test_superutilisateur_sans_second_facteur_bloque_sur_l_admin(client):
    su = get_user_model().objects.create_superuser("su@example.org", "su@example.org", "x")
    client.force_login(su)
    assert client.get("/admin/").status_code == 302


def test_inscription_libre_fermee(client):
    reponse = client.post(
        "/compte/signup/", {"email": "intrus@example.org", "password1": "x" * 20, "password2": "x" * 20}
    )
    assert "account/signup_closed.html" in [t.name for t in reponse.templates]
    assert not get_user_model().objects.filter(email="intrus@example.org").exists()


# Invitations
def test_invitation_cree_le_compte_une_seule_fois(client, demo):
    call_command("inviter", "Nouveau@example.org", Role.MEMBRE_CS, "--url", "https://copro.example.org")
    assert len(mail.outbox) == 1
    lien = next(ligne for ligne in mail.outbox[0].body.splitlines() if ligne.startswith("https://"))
    chemin = lien.removeprefix("https://copro.example.org")
    invitation = Invitation.objects.get()
    assert invitation.empreinte_jeton not in lien, "seule l'empreinte est stockée"

    mdp = "un-mot-de-passe-solide-2026"
    reponse = client.post(chemin, {"mot_de_passe": mdp, "confirmation": mdp})
    assert reponse.status_code == 302
    utilisateur = get_user_model().objects.get(email="nouveau@example.org")
    assert list(utilisateur.affectations.values_list("role", flat=True)) == [Role.MEMBRE_CS]
    # Connecté mais sans second facteur : renvoyé vers l'enrôlement.
    assert client.get(reverse("lots"))["Location"] == reverse("mfa_index")

    client.logout()
    assert client.get(chemin).status_code == 404


def test_invitation_expiree_refusee(client):
    invitation, jeton = Invitation.creer("tard@example.org", Role.MEMBRE_CS)
    Invitation.objects.filter(pk=invitation.pk).update(expire_le=timezone.now() - timedelta(seconds=1))
    assert client.get(reverse("accepter_invitation", args=[jeton])).status_code == 404


def test_invitation_mot_de_passe_faible_refuse(client):
    _, jeton = Invitation.creer("faible@example.org", Role.MEMBRE_CS)
    reponse = client.post(
        reverse("accepter_invitation", args=[jeton]), {"mot_de_passe": "1234", "confirmation": "1234"}
    )
    assert reponse.status_code == 200
    assert not get_user_model().objects.filter(email="faible@example.org").exists()


def test_invitation_pour_compte_existant_exige_son_titulaire(client):
    titulaire = _compte("deja@example.org", Role.MEMBRE_CS)
    _, jeton = Invitation.creer("deja@example.org", Role.CONTROLEUR)
    chemin = reverse("accepter_invitation", args=[jeton])
    client.force_login(_compte("autre@example.org", Role.MEMBRE_CS))
    assert client.post(chemin).status_code == 302
    assert not titulaire.affectations.filter(role=Role.CONTROLEUR).exists()
    client.force_login(titulaire)
    client.post(chemin)
    assert titulaire.affectations.filter(role=Role.CONTROLEUR).exists()

"""Essai dans un vrai navigateur (Chromium sans tête) : invitation → création
du compte → second facteur → incident, puis reconnexion. Couvre ce que le
client de test Django ne voit pas : pages d'allauth réellement rendues, CSP,
JavaScript du WebAuthn, enchaînement des redirections."""

import base64
import hashlib
import hmac
import struct
import time

import pytest
from django.core.management import call_command

from acces.models import Invitation, Role
from audit.models import Action, JournalAudit
from incidents.models import Incident

pytestmark = pytest.mark.django_db(transaction=True)

EMAIL = "nouveau@example.org"
MOT_DE_PASSE = "Un mot de passe solide 2026"


def totp(secret, pas=None):
    """Code TOTP (RFC 6238 : SHA-1, 30 s, 6 chiffres), calculé comme une
    application d'authentification, sans le code d'allauth."""
    pas = int(time.time() // 30) if pas is None else pas
    cle = base64.b32decode(secret + "=" * (-len(secret) % 8))
    condensat = hmac.new(cle, struct.pack(">Q", pas), hashlib.sha1).digest()
    decalage = condensat[-1] & 0x0F
    return f"{(struct.unpack('>I', condensat[decalage : decalage + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def _accepter_invitation(page):
    call_command("charger_demo")
    _, jeton = Invitation.creer(EMAIL, Role.MEMBRE_CS)
    page.goto(f"/invitation/{jeton}/")
    mots_de_passe = page.locator("input[type=password]")
    mots_de_passe.nth(0).fill(MOT_DE_PASSE)
    mots_de_passe.nth(1).fill(MOT_DE_PASSE)
    page.get_by_role("button", name="Créer le compte").click()


def _creer_incident(page, titre):
    page.goto("/incidents/nouveau/")
    page.get_by_label("Titre").fill(titre)
    page.get_by_label("Description").fill("Essai navigateur")
    page.get_by_role("button", name="Enregistrer").click()
    page.wait_for_load_state()
    assert Incident.objects.filter(titre=titre).exists()
    page.goto("/incidents/")
    assert page.get_by_text(titre).is_visible()


def test_invitation_totp_incident_puis_reconnexion(page):
    _accepter_invitation(page)
    # Compte créé, connecté, mais renvoyé vers le second facteur : rien
    # d'autre n'est accessible tant qu'il n'est pas enregistré.
    page.wait_for_url("**/compte/2fa/")
    page.goto("/incidents/")
    page.wait_for_url("**/compte/2fa/")

    page.get_by_role("link", name="Activer").click()
    if "/reauthenticate/" in page.url:  # cf. constat dans le BACKLOG
        page.locator("#id_password").fill(MOT_DE_PASSE)
        page.get_by_role("button", name="Confirmer").click()
    page.wait_for_url("**/2fa/totp/activate/")
    secret = page.locator("#authenticator_secret").input_value()
    pas_activation = int(time.time() // 30)
    page.get_by_label("Code de l'authentificateur").fill(totp(secret, pas_activation))
    page.get_by_role("button", name="Activer").click()
    page.wait_for_load_state()
    assert "/totp/activate/" not in page.url, page.content()

    _creer_incident(page, "Fuite en cave — essai navigateur")

    # Reconnexion : mot de passe puis code TOTP d'une autre fenêtre de 30 s
    # (un code déjà servi est refusé).
    page.get_by_role("button", name="Se déconnecter").click()
    page.wait_for_url("**/")
    page.goto("/compte/login/")
    page.locator("#id_login").fill(EMAIL)
    page.locator("#id_password").fill(MOT_DE_PASSE)
    page.get_by_role("button", name="Connexion").click()
    page.wait_for_url("**/2fa/authenticate/")
    while int(time.time() // 30) == pas_activation:
        time.sleep(0.5)
    page.locator("#id_code").fill(totp(secret))
    page.locator("form button[type=submit]").first.click()
    page.wait_for_url(lambda url: "/compte/" not in url)
    page.goto("/incidents/")
    assert page.get_by_text("Fuite en cave — essai navigateur").is_visible()

    actions = set(JournalAudit.objects.values_list("action", flat=True))
    assert {
        Action.INVITATION_CREEE,
        Action.INVITATION_ACCEPTEE,
        Action.SECOND_FACTEUR_AJOUTE,
        Action.CONNEXION,
        Action.DECONNEXION,
    } <= actions

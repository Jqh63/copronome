"""Mails sobres et reconnaissables : les trois voies d'envoi (invitation,
rappels d'échéances, mails d'allauth) portent le même pied — qui écrit, et
« nous ne demandons jamais de mot de passe par mail » — et aucun reste du
gabarit anglais d'allauth (« Hello from … »)."""

import datetime

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from acces.models import Role
from copro.models import Copropriete
from echeances.models import Echeance
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db
REGLE = "Nous ne vous demandons jamais votre mot de passe par mail."


@pytest.fixture(autouse=True)
def identite():
    Copropriete.objects.create(nom="Les Tilleuls", commune="Exempleville", code_insee="99999")


def _verifier_pied(message):
    corps = message.body
    assert corps.rstrip().endswith(REGLE), corps
    assert "Les Tilleuls (Exempleville), espace géré avec Copronome" in corps
    assert "Hello" not in corps and "Thank you" not in corps


def test_pied_de_l_invitation():
    call_command("inviter", "x@example.org", Role.MEMBRE_CS)
    (message,) = mail.outbox
    _verifier_pied(message)


def test_pied_des_rappels():
    _compte("cs@example.org", Role.MEMBRE_CS)
    Echeance.objects.create(
        titre="Contrôle ascenseur",
        type=Echeance.Type.CONTROLE,
        prochaine_le=timezone.localdate() + datetime.timedelta(days=5),
        periodicite_mois=12,
        rappel_jours=30,
    )
    call_command("envoyer_rappels")
    (message,) = mail.outbox
    _verifier_pied(message)


def test_pied_des_mails_allauth(client):
    _compte("p@example.org", Role.COPROPRIETAIRE)
    client.post("/compte/password/reset/", {"email": "p@example.org"})
    (message,) = mail.outbox
    _verifier_pied(message)
    assert message.body.startswith("Bonjour,")

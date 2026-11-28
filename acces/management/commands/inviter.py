"""Crée une invitation et envoie le lien par mail (le jeton n'est jamais stocké).

manage.py inviter <email> <role> [--batiment "Bâtiment A"] [--url https://copro.example.org]
"""

from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from acces.models import Invitation, Role
from copro.identite import expediteur, nom_affiche
from copro.models import Batiment


class Command(BaseCommand):
    help = "Invite une personne avec un rôle (lien valable 7 jours, à usage unique)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("role", choices=Role.values)
        parser.add_argument("--batiment", help="Nom du bâtiment ; absent = toute la copropriété")
        parser.add_argument("--url", default="http://localhost:8000", help="Adresse publique de l'instance")

    def handle(self, email, role, batiment=None, url="", **options):
        bat = None
        if batiment:
            bat = Batiment.objects.filter(nom=batiment).first()
            if bat is None:
                raise CommandError(f"Bâtiment inconnu : {batiment}")
        invitation, jeton = Invitation.creer(email, role, batiment=bat)
        lien = url.rstrip("/") + reverse("accepter_invitation", args=[jeton])
        send_mail(
            f"Invitation : {nom_affiche()}",
            f"Vous êtes invité·e sur l'espace de {nom_affiche()}, géré avec Copronome "
            f"({invitation.get_role_display()}).\n\n"
            f"Créez votre compte avec ce lien, valable 7 jours et utilisable une seule fois :\n{lien}\n",
            expediteur(),
            [invitation.email],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Invitation envoyée à {invitation.email} (expire le {invitation.expire_le:%d/%m/%Y})."
            )
        )

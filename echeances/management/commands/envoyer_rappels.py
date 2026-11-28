"""Rappels d'échéances par mail, à lancer une fois par jour par un timer
(ADR, tâches planifiées). Un mail par destinataire, qui liste les échéances
de son périmètre entrées dans leur fenêtre de rappel. Chaque échéance n'est
rappelée qu'une fois par date d'échéance (`rappel_envoye_pour`) : relancer
la commande le même jour n'envoie rien de plus.

Destinataires : les comptes actifs qui peuvent ÉCRIRE les échéances (ceux
qui peuvent agir), jamais l'admin technique seul.
"""

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from acces.droits import ECRIRE, peut
from copro.identite import expediteur, nom_affiche, pied_de_mail
from echeances.models import Echeance
from echeances.views import visibles


class Command(BaseCommand):
    help = "Envoie les rappels d'échéances arrivées dans leur fenêtre de rappel."

    def add_arguments(self, parser):
        parser.add_argument("--url", default="", help="Adresse publique de l'instance, pour les liens")

    def handle(self, *args, url, **options):
        aujourdhui = timezone.localdate()
        dues = list(
            Echeance.objects.filter(active=True)
            .exclude(rappel_envoye_pour=F("prochaine_le"))
            .order_by("prochaine_le")
        )
        dues = [e for e in dues if e.date_rappel() <= aujourdhui]
        if not dues:
            return
        ids_dues = {e.pk for e in dues}
        nom, de, pied = nom_affiche(), expediteur(), pied_de_mail()
        envoyes, rappelees = 0, set()
        for utilisateur in get_user_model().objects.filter(is_active=True).prefetch_related("affectations"):
            if not peut(utilisateur, ECRIRE, "echeances"):
                continue
            siennes = list(visibles(utilisateur, ECRIRE).filter(pk__in=ids_dues).order_by("prochaine_le"))
            if not siennes or not utilisateur.email:
                continue
            lignes = []
            for e in siennes:
                etat = "EN RETARD" if e.en_retard(aujourdhui) else "à venir"
                lien = f"\n    {url.rstrip('/')}{reverse('echeances:detail', args=[e.pk])}" if url else ""
                lignes.append(f"- {e.prochaine_le:%d/%m/%Y} ({etat}) : {e.titre}{lien}")
            send_mail(
                f"{nom} : {len(siennes)} échéance(s) à traiter",
                "Échéances arrivées dans leur fenêtre de rappel :\n\n" + "\n".join(lignes) + "\n\n" + pied,
                de,
                [utilisateur.email],
            )
            envoyes += 1
            rappelees.update(e.pk for e in siennes)
        # Une échéance sans destinataire n'est pas marquée : elle repart demain.
        for e in dues:
            if e.pk not in rappelees:
                continue
            e.rappel_envoye_pour = e.prochaine_le
            e.save(update_fields=["rappel_envoye_pour"])
        self.stdout.write(f"{len(rappelees)} échéance(s) rappelée(s), {envoyes} mail(s) envoyé(s).")

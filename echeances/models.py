"""Échéances et leurs réalisations (ADR de conception, § 3).

Aucune fréquence légale n'est écrite ici : la périodicité et le texte qui
fonde l'échéance (`reference`) sont saisis par le conseil syndical. Une
bibliothèque de contrôles types n'entrera qu'avec la source de chaque
fréquence (CLAUDE.md, principes de code).

Les réalisations forment un journal en ajout seul ; la date de la prochaine
échéance ne change que par une réalisation.
"""

import calendar
import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from copro.models import Batiment, PartieCommune


def ajouter_mois(date, mois):
    """Même jour `mois` mois plus tard, ramené au dernier jour du mois si besoin."""
    total = date.month - 1 + mois
    annee, mois_suivant = date.year + total // 12, total % 12 + 1
    jour = min(date.day, calendar.monthrange(annee, mois_suivant)[1])
    return datetime.date(annee, mois_suivant, jour)


class Echeance(models.Model):
    class Type(models.TextChoices):
        CONTROLE = "controle", "Contrôle ou entretien réglementaire"
        CONTRAT = "contrat", "Fin ou préavis de contrat"
        ASSURANCE = "assurance", "Assurance"
        MANDAT = "mandat", "Mandat (syndic, conseil syndical)"
        AG = "ag", "Assemblée générale"
        TRAVAUX = "travaux", "Travaux et plan pluriannuel"
        AUTRE = "autre", "Autre"

    titre = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=Type.choices)
    prochaine_le = models.DateField("prochaine échéance")
    periodicite_mois = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Vide = échéance ponctuelle"
    )
    rappel_jours = models.PositiveSmallIntegerField(default=30, help_text="Rappel par mail N jours avant")
    reference = models.CharField(
        max_length=300, blank=True, help_text="Texte, article ou contrat qui fonde l'échéance"
    )
    notes = models.TextField(blank=True)
    batiment = models.ForeignKey(
        Batiment, null=True, blank=True, on_delete=models.PROTECT, help_text="Vide = toute la copropriété"
    )
    partie_commune = models.ForeignKey(PartieCommune, null=True, blank=True, on_delete=models.PROTECT)
    active = models.BooleanField(default=True, editable=False)
    rappel_envoye_pour = models.DateField(null=True, blank=True, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["prochaine_le", "titre"]
        verbose_name = "échéance"

    def __str__(self):
        return self.titre

    def clean(self):
        source = self.partie_commune
        if source is not None and source.batiment_id is not None:
            if self.batiment_id is None:
                self.batiment_id = source.batiment_id
            elif self.batiment_id != source.batiment_id:
                raise ValidationError("La partie commune appartient à un autre bâtiment que celui choisi.")

    def date_rappel(self):
        return self.prochaine_le - datetime.timedelta(days=self.rappel_jours)

    def en_retard(self, aujourdhui):
        return self.active and self.prochaine_le < aujourdhui


class RealisationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Journal en ajout seul : modification refusée.")

    def delete(self):
        raise ValidationError("Journal en ajout seul : suppression refusée.")


class Realisation(models.Model):
    echeance = models.ForeignKey(Echeance, on_delete=models.PROTECT, related_name="realisations")
    realisee_le = models.DateField()
    pour_echeance_du = models.DateField(help_text="Échéance que cette réalisation solde")
    note = models.TextField(blank=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    objects = RealisationQuerySet.as_manager()

    class Meta:
        ordering = ["-realisee_le", "-pk"]
        verbose_name = "réalisation"

    def __str__(self):
        return f"{self.echeance} — {self.realisee_le:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Journal en ajout seul : modification refusée.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Journal en ajout seul : suppression refusée.")


@transaction.atomic
def realiser(echeance, realisee_le, auteur, note=""):
    """Seul chemin qui solde une échéance : journalise la réalisation, puis
    reporte la prochaine date (périodicité comptée depuis la réalisation)
    ou clôt une échéance ponctuelle."""
    if not echeance.active:
        raise ValidationError("Échéance déjà close.")
    realisation = Realisation.objects.create(
        echeance=echeance,
        realisee_le=realisee_le,
        pour_echeance_du=echeance.prochaine_le,
        note=note,
        auteur=auteur,
    )
    if echeance.periodicite_mois:
        echeance.prochaine_le = ajouter_mois(realisee_le, echeance.periodicite_mois)
    else:
        echeance.active = False
    echeance.rappel_envoye_pour = None
    echeance.save(update_fields=["prochaine_le", "active", "rappel_envoye_pour"])
    return realisation

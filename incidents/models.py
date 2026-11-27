"""Incidents et leur journal (ADR de conception, § 3).

Le journal est en ajout seul : un événement ne se modifie ni ne se
supprime, et le statut d'un incident ne change que par un événement.
Le nom de la personne qui signale n'est jamais public (ADR, § 3).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from copro.models import Batiment, Lot, PartieCommune


class Statut(models.TextChoices):
    NOUVEAU = "nouveau", "Nouveau"
    TRANSMIS = "transmis", "Transmis au syndic"
    EN_COURS = "en_cours", "En cours"
    RESOLU = "resolu", "Résolu"
    CLOS = "clos", "Clos"


class Incident(models.Model):
    class Priorite(models.TextChoices):
        BASSE = "basse", "Basse"
        NORMALE = "normale", "Normale"
        HAUTE = "haute", "Haute"
        URGENTE = "urgente", "Urgente"

    titre = models.CharField(max_length=200)
    description = models.TextField()
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.NOUVEAU, editable=False)
    priorite = models.CharField(max_length=20, choices=Priorite.choices, default=Priorite.NORMALE)
    batiment = models.ForeignKey(
        Batiment, null=True, blank=True, on_delete=models.PROTECT, help_text="Vide = toute la copropriété"
    )
    partie_commune = models.ForeignKey(PartieCommune, null=True, blank=True, on_delete=models.PROTECT)
    lot = models.ForeignKey(Lot, null=True, blank=True, on_delete=models.PROTECT)
    prestataire = models.CharField(max_length=200, blank=True)
    transmis_syndic_le = models.DateField(null=True, blank=True, editable=False)
    relance_prevue_le = models.DateField(null=True, blank=True, help_text="Date de relance du syndic")
    signale_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    maj_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "incident"

    def __str__(self):
        return self.titre

    def clean(self):
        # Le bâtiment se déduit de la localisation ; il doit lui être cohérent.
        for source in (self.lot, self.partie_commune):
            if source is not None and source.batiment_id is not None:
                if self.batiment_id is None:
                    self.batiment_id = source.batiment_id
                elif self.batiment_id != source.batiment_id:
                    raise ValidationError("La localisation appartient à un autre bâtiment que celui choisi.")


class EvenementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Journal en ajout seul : modification refusée.")

    def delete(self):
        raise ValidationError("Journal en ajout seul : suppression refusée.")


class Evenement(models.Model):
    class Type(models.TextChoices):
        CREATION = "creation", "Création"
        COMMENTAIRE = "commentaire", "Commentaire"
        STATUT = "statut", "Changement de statut"
        TRANSMISSION = "transmission", "Transmission au syndic"
        RELANCE = "relance", "Relance du syndic"
        REPONSE_SYNDIC = "reponse_syndic", "Réponse du syndic"

    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="evenements")
    type = models.CharField(max_length=20, choices=Type.choices)
    texte = models.TextField(blank=True)
    nouveau_statut = models.CharField(max_length=20, choices=Statut.choices, blank=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    objects = EvenementQuerySet.as_manager()

    class Meta:
        ordering = ["cree_le", "pk"]
        verbose_name = "événement"

    def __str__(self):
        return f"{self.get_type_display()} — {self.incident}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Journal en ajout seul : modification refusée.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Journal en ajout seul : suppression refusée.")


# Statut qu'impose chaque type d'événement (vide = inchangé).
STATUT_IMPOSE = {Evenement.Type.TRANSMISSION: Statut.TRANSMIS}


@transaction.atomic
def journaliser(incident, type, auteur, texte="", nouveau_statut=""):
    """Seul chemin d'écriture du journal : ajoute l'événement et applique
    son effet sur l'incident (statut, date de transmission)."""
    nouveau_statut = STATUT_IMPOSE.get(type, nouveau_statut)
    if type == Evenement.Type.STATUT and not nouveau_statut:
        raise ValidationError("Un changement de statut doit indiquer le nouveau statut.")
    evenement = Evenement.objects.create(
        incident=incident, type=type, auteur=auteur, texte=texte, nouveau_statut=nouveau_statut or ""
    )
    champs = []
    if nouveau_statut and nouveau_statut != incident.statut:
        incident.statut = nouveau_statut
        champs.append("statut")
    if type == Evenement.Type.TRANSMISSION and incident.transmis_syndic_le is None:
        incident.transmis_syndic_le = evenement.cree_le.date()
        champs.append("transmis_syndic_le")
    if champs:
        incident.save(update_fields=[*champs, "maj_le"])
    return evenement

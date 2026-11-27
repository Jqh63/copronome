"""Agenda du conseil syndical et lien iCal personnel (ADR de conception, § 3).

Le lien iCal porte un jeton : seule son empreinte SHA-256 est stockée, un
compte n'a qu'un lien à la fois, et en générer un nouveau révoque l'ancien.
"""

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from acces.models import empreinte
from copro.models import Batiment
from incidents.models import Incident


class Evenement(models.Model):
    titre = models.CharField(max_length=200)
    debut = models.DateTimeField("début")
    fin = models.DateTimeField(null=True, blank=True)
    lieu = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    batiment = models.ForeignKey(
        Batiment, null=True, blank=True, on_delete=models.PROTECT, help_text="Vide = toute la copropriété"
    )
    incident = models.ForeignKey(
        Incident, null=True, blank=True, on_delete=models.PROTECT, related_name="rendez_vous"
    )
    annule = models.BooleanField("annulé", default=False)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    maj_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["debut"]
        verbose_name = "événement d'agenda"

    def __str__(self):
        return self.titre

    def clean(self):
        if self.fin and self.debut and self.fin < self.debut:
            raise ValidationError("La fin précède le début.")
        if self.incident is not None and self.incident.batiment_id is not None:
            if self.batiment_id is None:
                self.batiment_id = self.incident.batiment_id
            elif self.batiment_id != self.incident.batiment_id:
                raise ValidationError("L'incident lié appartient à un autre bâtiment que celui choisi.")


class JetonAgenda(models.Model):
    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jeton_agenda"
    )
    empreinte_jeton = models.CharField(max_length=64, unique=True, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "lien iCal"

    def __str__(self):
        return f"Lien iCal de {self.utilisateur}"

    @classmethod
    @transaction.atomic
    def generer(cls, utilisateur):
        """Remplace le lien du compte et renvoie le jeton en clair, qui n'est
        plus récupérable ensuite."""
        cls.objects.filter(utilisateur=utilisateur).delete()
        jeton = secrets.token_urlsafe(32)
        cls.objects.create(utilisateur=utilisateur, empreinte_jeton=empreinte(jeton))
        return jeton

    @classmethod
    def trouver(cls, jeton):
        return cls.objects.select_related("utilisateur").filter(empreinte_jeton=empreinte(jeton)).first()

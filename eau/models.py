"""Compteurs d'eau et relevés d'index.

Copronome ne répartit pas l'eau en euros : le logiciel de comptabilité
(Diacamma Syndic, ou celui du syndic) le fait sur une clé dont les tantièmes
sont les m³ de l'exercice. Ici, le conseil syndical relève les index, les
compare à ceux du syndic, repère les anomalies et sort les m³ par lot.

Les relevés forment un journal en ajout seul (ORM et trigger Postgres) : un
relevé erroné ne se modifie pas, un nouveau relevé le corrige (`corrige`) et
le relevé corrigé sort des calculs.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from copro.models import Lot, PartieCommune


class Compteur(models.Model):
    numero = models.CharField(max_length=40, unique=True, help_text="Numéro inscrit sur le compteur")
    lot = models.ForeignKey(
        Lot, null=True, blank=True, on_delete=models.PROTECT, related_name="compteurs_eau"
    )
    partie_commune = models.ForeignKey(
        PartieCommune, null=True, blank=True, on_delete=models.PROTECT, related_name="compteurs_eau"
    )
    emplacement = models.CharField(max_length=200, blank=True, help_text="Ex. : gaine palière, 2ᵉ étage")
    actif = models.BooleanField(default=True, help_text="Décocher quand le compteur est déposé ou remplacé")

    class Meta:
        ordering = ["numero"]
        verbose_name = "compteur d'eau"
        verbose_name_plural = "compteurs d'eau"
        constraints = [
            models.CheckConstraint(
                condition=Q(lot__isnull=False, partie_commune__isnull=True)
                | Q(lot__isnull=True, partie_commune__isnull=False),
                name="compteur_lot_ou_partie_commune",
            )
        ]

    def __str__(self):
        return f"Compteur {self.numero}"

    @property
    def batiment_id(self):
        # Périmètre du contrôle d'accès (acces.droits) : celui du lot ou de la partie commune.
        if self.lot_id is not None:
            return self.lot.batiment_id
        if self.partie_commune_id is not None:
            return self.partie_commune.batiment_id
        return None

    @property
    def lieu(self):
        return f"Lot {self.lot.numero}" if self.lot_id else str(self.partie_commune)

    def clean(self):
        if (self.lot_id is None) == (self.partie_commune_id is None):
            raise ValidationError("Un compteur dessert soit un lot, soit une partie commune.")

    def releves_valides(self):
        """Relevés non corrigés, du plus ancien au plus récent."""
        return self.releves.filter(correction__isnull=True).order_by("releve_le", "saisi_le", "pk")


class ReleveQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Journal en ajout seul : modification refusée.")

    def delete(self):
        raise ValidationError("Journal en ajout seul : suppression refusée.")


class Releve(models.Model):
    class Source(models.TextChoices):
        CS = "cs", "Conseil syndical"
        SYNDIC = "syndic", "Syndic ou prestataire"
        AUTRE = "autre", "Autre"

    compteur = models.ForeignKey(Compteur, on_delete=models.PROTECT, related_name="releves")
    releve_le = models.DateField("relevé le")
    index = models.DecimalField(
        "index (m³)", max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal("0"))]
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.CS)
    note = models.CharField(max_length=200, blank=True)
    corrige = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="correction",
        help_text="Relevé erroné que celui-ci remplace",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    saisi_le = models.DateTimeField(auto_now_add=True)

    objects = ReleveQuerySet.as_manager()

    class Meta:
        ordering = ["releve_le", "saisi_le", "pk"]
        verbose_name = "relevé d'index"
        verbose_name_plural = "relevés d'index"

    def __str__(self):
        return f"{self.compteur} : {self.index} m³ le {self.releve_le:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Journal en ajout seul : modification refusée.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Journal en ajout seul : suppression refusée.")

    def clean(self):
        if self.corrige_id is not None and self.corrige.compteur_id != self.compteur_id:
            raise ValidationError("Une correction porte sur un relevé du même compteur.")


def historique(compteur):
    """Relevés valides avec la consommation depuis le précédent et l'anomalie
    éventuelle (index en baisse : erreur de lecture ou compteur changé)."""
    lignes, precedent = [], None
    for releve in compteur.releves_valides():
        ligne = {"releve": releve, "m3": None, "jours": None, "baisse": False}
        if precedent is not None:
            ligne["m3"] = releve.index - precedent.index
            ligne["jours"] = (releve.releve_le - precedent.releve_le).days
            ligne["baisse"] = ligne["m3"] < 0
        lignes.append(ligne)
        precedent = releve
    return lignes


def consommation(compteur, debut, fin):
    """m³ d'un compteur entre deux dates, et les relevés qui la fondent.

    Index de début : dernier relevé valide au plus tard le jour `debut` ; à
    défaut, premier relevé de la période (compteur posé en cours d'exercice).
    Index de fin : dernier relevé valide au plus tard le jour `fin`.
    Renvoie (None, début, fin) si l'un manque : la consommation n'est jamais
    devinée.
    """
    releves = compteur.releves_valides()
    releve_debut = releves.filter(releve_le__lte=debut).last()
    if releve_debut is None:
        releve_debut = releves.filter(releve_le__gt=debut, releve_le__lte=fin).first()
    releve_fin = releves.filter(releve_le__lte=fin).last()
    if releve_debut is None or releve_fin is None or releve_fin.pk == releve_debut.pk:
        return None, releve_debut, releve_fin
    return releve_fin.index - releve_debut.index, releve_debut, releve_fin

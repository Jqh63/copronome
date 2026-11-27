"""Structure de la copropriété, répartition et personnes (ADR de conception, § 3).

Une instance = une copropriété : aucun modèle « Copropriété » ni filtre par
copropriété. Les escaliers, ascenseurs et parkings sont des parties
communes, pas des entités figées. Les tantièmes sont lus (votes,
affectations), jamais utilisés pour calculer des charges.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class Batiment(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    ordre = models.PositiveSmallIntegerField(default=0, help_text="Ordre d'affichage")

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "bâtiment"

    def __str__(self):
        return self.nom


class PartieCommune(models.Model):
    class Type(models.TextChoices):
        ESCALIER = "escalier", "Escalier"
        ASCENSEUR = "ascenseur", "Ascenseur"
        PARKING = "parking", "Parking"
        HALL = "hall", "Hall"
        CAVES = "caves", "Caves"
        TOITURE = "toiture", "Toiture"
        ESPACE_VERT = "espace_vert", "Espace vert"
        LOCAL = "local", "Local technique ou commun"
        AUTRE = "autre", "Autre"

    nom = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=Type.choices)
    batiment = models.ForeignKey(
        Batiment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="parties_communes",
        help_text="Vide = commune à toute la copropriété",
    )

    class Meta:
        ordering = ["batiment__ordre", "nom"]
        verbose_name = "partie commune"
        verbose_name_plural = "parties communes"
        constraints = [
            models.UniqueConstraint(fields=["batiment", "nom"], name="partie_commune_unique_par_batiment"),
            models.UniqueConstraint(
                fields=["nom"], condition=Q(batiment__isnull=True), name="partie_commune_generale_unique"
            ),
        ]

    def __str__(self):
        return f"{self.nom} ({self.batiment})" if self.batiment else self.nom


class Lot(models.Model):
    class Type(models.TextChoices):
        LOGEMENT = "logement", "Logement"
        PARKING = "parking", "Parking"
        CAVE = "cave", "Cave"
        LOCAL = "local", "Local commercial ou professionnel"
        AUTRE = "autre", "Autre"

    numero = models.CharField(max_length=20, unique=True, help_text="Numéro au règlement de copropriété")
    type = models.CharField(max_length=20, choices=Type.choices)
    batiment = models.ForeignKey(Batiment, on_delete=models.PROTECT, related_name="lots")
    etage = models.SmallIntegerField(
        null=True, blank=True, help_text="0 = rez-de-chaussée, négatif = sous-sol"
    )
    escalier = models.ForeignKey(
        PartieCommune,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lots_desservis",
        limit_choices_to={"type": PartieCommune.Type.ESCALIER},
    )
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["batiment__ordre", "numero"]
        verbose_name = "lot"

    def __str__(self):
        return f"Lot {self.numero} ({self.get_type_display().lower()}, {self.batiment})"

    def clean(self):
        if self.escalier_id and self.escalier.type != PartieCommune.Type.ESCALIER:
            raise ValidationError({"escalier": "Choisir une partie commune de type escalier."})
        if self.escalier_id and self.escalier.batiment_id not in (None, self.batiment_id):
            raise ValidationError({"escalier": "Cet escalier appartient à un autre bâtiment."})

    def detentions_actives(self, date=None):
        return self.detentions.actives(date)


class CleRepartition(models.Model):
    nom = models.CharField(max_length=100, unique=True, help_text="Ex. : charges générales, ascenseur bât. B")
    base = models.PositiveIntegerField(default=10000, help_text="Total des tantièmes de la clé")
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "clé de répartition"
        verbose_name_plural = "clés de répartition"

    def __str__(self):
        return self.nom

    def total_attribue(self):
        return self.tantiemes.aggregate(total=Sum("valeur"))["total"] or 0

    def est_complete(self):
        """Vrai quand la somme des tantièmes atteint exactement la base."""
        return self.total_attribue() == self.base


class Tantieme(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="tantiemes")
    cle = models.ForeignKey(CleRepartition, on_delete=models.PROTECT, related_name="tantiemes")
    valeur = models.PositiveIntegerField()

    class Meta:
        ordering = ["cle__nom", "lot__numero"]
        verbose_name = "tantième"
        constraints = [models.UniqueConstraint(fields=["lot", "cle"], name="tantieme_unique_par_lot_et_cle")]

    def __str__(self):
        return f"{self.lot.numero} : {self.valeur}/{self.cle.base} ({self.cle})"

    def clean(self):
        if not self.cle_id or self.valeur is None:
            return
        autres = self.cle.tantiemes.exclude(pk=self.pk).aggregate(total=Sum("valeur"))["total"] or 0
        if autres + self.valeur > self.cle.base:
            raise ValidationError(
                {"valeur": f"Dépasse la base de la clé : {autres} déjà attribués sur {self.cle.base}."}
            )


class Personne(models.Model):
    class Type(models.TextChoices):
        PHYSIQUE = "physique", "Personne physique"
        MORALE = "morale", "Personne morale"

    type = models.CharField(max_length=10, choices=Type.choices, default=Type.PHYSIQUE)
    nom = models.CharField(max_length=150, help_text="Nom de famille, ou raison sociale")
    prenom = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=30, blank=True)
    adresse_postale = models.TextField(blank=True, help_text="Pour les envois papier")
    notes = models.TextField(blank=True)
    efface_le = models.DateField(
        null=True, blank=True, editable=False, help_text="Coordonnées effacées par la purge (copro.purge)"
    )

    class Meta:
        ordering = ["nom", "prenom"]
        verbose_name = "personne"

    def __str__(self):
        if self.efface_le:
            return f"Personne effacée n° {self.pk}"
        return f"{self.prenom} {self.nom}".strip()

    def clean(self):
        if self.type == self.Type.MORALE and self.prenom:
            raise ValidationError({"prenom": "Une personne morale n'a pas de prénom."})


class PeriodeQuerySet(models.QuerySet):
    def actives(self, date=None):
        date = date or timezone.localdate()
        return self.filter(debut__lte=date).filter(Q(fin__isnull=True) | Q(fin__gte=date))


class Periode(models.Model):
    debut = models.DateField()
    fin = models.DateField(null=True, blank=True, help_text="Vide = en cours")

    objects = PeriodeQuerySet.as_manager()

    class Meta:
        abstract = True

    def clean(self):
        if self.debut and self.fin and self.fin < self.debut:
            raise ValidationError({"fin": "La fin précède le début."})


class Detention(Periode):
    """Droit d'une personne sur un lot. Le mandataire commun d'une indivision
    (qui porte le vote) n'est pas encore modélisé (ADR § 3, hors MVP)."""

    class Nature(models.TextChoices):
        PLEINE_PROPRIETE = "pleine_propriete", "Pleine propriété"
        INDIVISION = "indivision", "Indivision"
        USUFRUIT = "usufruit", "Usufruit"
        NUE_PROPRIETE = "nue_propriete", "Nue-propriété"

    personne = models.ForeignKey(Personne, on_delete=models.PROTECT, related_name="detentions")
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="detentions")
    nature = models.CharField(max_length=20, choices=Nature.choices, default=Nature.PLEINE_PROPRIETE)
    quote_part_numerateur = models.PositiveIntegerField(default=1)
    quote_part_denominateur = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["lot__numero", "-debut"]
        verbose_name = "détention"
        constraints = [
            models.CheckConstraint(
                condition=Q(quote_part_numerateur__gt=0)
                & Q(quote_part_numerateur__lte=models.F("quote_part_denominateur")),
                name="detention_quote_part_entre_0_et_1",
            ),
            models.CheckConstraint(
                condition=Q(fin__isnull=True) | Q(fin__gte=models.F("debut")),
                name="detention_periode_ordonnee",
            ),
        ]

    def __str__(self):
        return f"{self.personne} — lot {self.lot.numero} ({self.get_nature_display().lower()})"

    @property
    def quote_part(self):
        return f"{self.quote_part_numerateur}/{self.quote_part_denominateur}"

    def clean(self):
        super().clean()
        if self.quote_part_denominateur and not (
            0 < self.quote_part_numerateur <= self.quote_part_denominateur
        ):
            raise ValidationError("La quote-part doit être comprise entre 0 (exclu) et 1.")


class Occupation(Periode):
    class Type(models.TextChoices):
        LOCATAIRE = "locataire", "Locataire"
        OCCUPANT = "occupant", "Occupant à titre gratuit"

    personne = models.ForeignKey(Personne, on_delete=models.PROTECT, related_name="occupations")
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="occupations")
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.LOCATAIRE)

    class Meta:
        ordering = ["lot__numero", "-debut"]
        verbose_name = "occupation"
        constraints = [
            models.CheckConstraint(
                condition=Q(fin__isnull=True) | Q(fin__gte=models.F("debut")),
                name="occupation_periode_ordonnee",
            ),
        ]

    def __str__(self):
        return f"{self.personne} — lot {self.lot.numero} ({self.get_type_display().lower()})"

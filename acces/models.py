"""Rôles par périmètre et invitations (ADR de conception, § 4).

Un droit = une paire (rôle, périmètre). Le périmètre est la copropriété
entière (bâtiment vide) ou un bâtiment. Un compte peut cumuler des paires.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from copro.models import Batiment, Personne


class Role(models.TextChoices):
    ADMIN = "admin", "Admin technique"
    PRESIDENT = "president", "Président du conseil syndical"
    MEMBRE_CS = "membre_cs", "Membre du conseil syndical"
    CONTROLEUR = "controleur", "Contrôleur des comptes"
    SYNDIC = "syndic", "Syndic professionnel"
    COPROPRIETAIRE = "coproprietaire", "Copropriétaire"


# Rôles qui écrivent ou voient tout : second facteur obligatoire (ADR, § 5).
ROLES_MFA_OBLIGATOIRE = {Role.ADMIN, Role.PRESIDENT, Role.MEMBRE_CS, Role.CONTROLEUR, Role.SYNDIC}


class Affectation(models.Model):
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="affectations"
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    batiment = models.ForeignKey(
        Batiment, null=True, blank=True, on_delete=models.PROTECT, help_text="Vide = toute la copropriété"
    )
    personne = models.ForeignKey(
        Personne,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Fiche de la personne, si connue",
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "affectation"
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "role", "batiment"], name="affectation_unique", nulls_distinct=False
            )
        ]

    def __str__(self):
        return f"{self.utilisateur} — {self.get_role_display()} ({self.batiment or 'toute la copropriété'})"


def empreinte(jeton):
    return hashlib.sha256(jeton.encode()).hexdigest()


class Invitation(models.Model):
    """Invitation à usage unique. Seule l'empreinte SHA-256 du jeton est
    stockée : une fuite de la base ne donne pas de lien utilisable."""

    DUREE = timedelta(days=7)

    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Role.choices)
    batiment = models.ForeignKey(Batiment, null=True, blank=True, on_delete=models.PROTECT)
    empreinte_jeton = models.CharField(max_length=64, unique=True, editable=False)
    expire_le = models.DateTimeField(editable=False)
    creee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="invitations_creees"
    )
    creee_le = models.DateTimeField(auto_now_add=True)
    utilisee_le = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "invitation"
        ordering = ["-creee_le"]

    def __str__(self):
        return f"{self.email} — {self.get_role_display()}"

    @classmethod
    def creer(cls, email, role, batiment=None, creee_par=None):
        """Crée l'invitation et renvoie (invitation, jeton en clair) ; le
        jeton n'est plus récupérable ensuite."""
        jeton = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            email=email.strip().lower(),
            role=role,
            batiment=batiment,
            creee_par=creee_par,
            empreinte_jeton=empreinte(jeton),
            expire_le=timezone.now() + cls.DUREE,
        )
        return invitation, jeton

    @classmethod
    def valide(cls, jeton):
        """Invitation utilisable pour ce jeton, ou None."""
        return cls.objects.filter(
            empreinte_jeton=empreinte(jeton), utilisee_le__isnull=True, expire_le__gt=timezone.now()
        ).first()

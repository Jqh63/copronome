"""Journal d'audit : qui, quoi, quand, sur quel objet (ADR de conception, § 3).

En ajout seul à deux niveaux : l'ORM refuse toute modification, et sous
Postgres un trigger refuse UPDATE, DELETE et TRUNCATE (migration 0002), y
compris par SQL brut. L'acteur est copié au moment de l'action
(`acteur_nom`) et le lien vers son compte n'est pas une clé étrangère : la
suppression d'un compte ne réécrit pas le journal.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Action(models.TextChoices):
    CONNEXION = "connexion", "Connexion"
    CONNEXION_ECHEC = "connexion_echec", "Échec de connexion"
    DECONNEXION = "deconnexion", "Déconnexion"
    SECOND_FACTEUR_AJOUTE = "second_facteur_ajoute", "Second facteur ajouté"
    SECOND_FACTEUR_RETIRE = "second_facteur_retire", "Second facteur retiré"
    SECOND_FACTEUR_ECHEC = "second_facteur_echec", "Échec du second facteur"
    MOT_DE_PASSE_CHANGE = "mot_de_passe_change", "Mot de passe changé"
    MOT_DE_PASSE_REINITIALISE = "mot_de_passe_reinitialise", "Mot de passe réinitialisé"
    INVITATION_CREEE = "invitation_creee", "Invitation créée"
    INVITATION_ACCEPTEE = "invitation_acceptee", "Invitation acceptée"
    DOCUMENT_DEPOSE = "document_depose", "Document déposé"
    DOCUMENT_REMPLACE = "document_remplace", "Document remplacé"
    DOCUMENT_RETIRE = "document_retire", "Document retiré"


class JournalAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Journal en ajout seul : modification refusée.")

    def delete(self):
        raise ValidationError("Journal en ajout seul : suppression refusée.")


class JournalAudit(models.Model):
    cree_le = models.DateTimeField(auto_now_add=True)
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    acteur_nom = models.CharField(max_length=254, blank=True)
    action = models.CharField(max_length=40, choices=Action.choices)
    objet_type = models.CharField(max_length=60, blank=True)
    objet_id = models.CharField(max_length=40, blank=True)
    objet_libelle = models.CharField(max_length=255, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    objects = JournalAuditQuerySet.as_manager()

    class Meta:
        ordering = ["-cree_le", "-pk"]
        verbose_name = "entrée du journal d'audit"
        verbose_name_plural = "journal d'audit"

    def __str__(self):
        return f"{self.cree_le:%d/%m/%Y %H:%M} {self.acteur_nom or '—'} {self.get_action_display()}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Journal en ajout seul : modification refusée.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Journal en ajout seul : suppression refusée.")


def journaliser(action, acteur=None, objet=None, acteur_nom="", **detail):
    """Ajoute une entrée. `acteur` = compte qui agit (None = système ou
    anonyme, alors `acteur_nom` peut porter l'identifiant tenté) ; `objet` =
    instance concernée ; `detail` = données utiles, jamais un secret ni un jeton."""
    if acteur is not None and not getattr(acteur, "is_authenticated", False):
        acteur = None
    return JournalAudit.objects.create(
        action=action,
        acteur=acteur,
        acteur_nom=(acteur.get_username() if acteur is not None else acteur_nom)[:254],
        objet_type=objet._meta.label_lower if objet is not None else "",
        objet_id=str(objet.pk) if objet is not None else "",
        objet_libelle=str(objet)[:255] if objet is not None else "",
        detail=detail,
    )

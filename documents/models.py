"""Documents de la copropriété (ADR de conception, § 3 et modèle de menace).

Un fichier déposé n'est jamais servi par une URL statique : il passe par la
vue `telecharger`, qui vérifie le droit sur l'objet et l'envoie en
`attachment`. Sur disque, il porte un nom aléatoire et l'extension du type
détecté, jamais le nom fourni par le navigateur.
"""

import hashlib
import uuid

from django.conf import settings
from django.db import models

from copro.models import Batiment
from documents.validation import TYPES


class Categorie(models.TextChoices):
    # Catégories du décret n° 2019-502 du 23 mai 2019 (liste minimale de
    # l'espace en ligne du syndic), reprises comme référentiel : elles
    # n'obligent pas un syndic non professionnel. Source : ANIL, « Copropriété :
    # dématérialisation des documents » (à jour au 2019-05-28) et INC, « le
    # contenu de l'espace sécurisé en ligne » (2019-08-13), concordants.
    # Légifrance (JORFTEXT000038501555) signale une version de l'art. 1 en
    # vigueur depuis le 2020-10-10, non lue (page protégée) : à relire.
    #
    # Art. 1, ensemble des copropriétaires :
    REGLEMENT = "reglement", "Règlement de copropriété, état descriptif de division et modificatifs"
    FICHE_SYNTHETIQUE = "fiche_synthetique", "Fiche synthétique"
    CARNET_ENTRETIEN = "carnet_entretien", "Carnet d'entretien"
    DIAGNOSTICS = "diagnostics", "Diagnostics techniques des parties communes"
    ASSURANCE = "assurance", "Contrats d'assurance de l'immeuble"
    CONTRATS = "contrats", "Contrats et marchés signés par le syndic"
    CONTRATS_ENTRETIEN = "contrats_entretien", "Contrats d'entretien et maintenance des équipements communs"
    PV_AG = "pv_ag", "Procès-verbaux d'assemblée générale et devis approuvés"
    CONTRAT_SYNDIC = "contrat_syndic", "Contrat de syndic"
    # Art. 3, membres du conseil syndical :
    COMPTES = "comptes", "Balances générales, relevé des charges et produits de l'exercice"
    RELEVES_BANCAIRES = "releves_bancaires", "Relevés du compte bancaire séparé"
    CONTENTIEUX = "contentieux", "Assignations et décisions de justice en cours"
    LISTE_COPROPRIETAIRES = "liste_coproprietaires", "Liste des copropriétaires"
    ATTESTATIONS_SYNDIC = "attestations_syndic", "Carte professionnelle, assurance et garantie du syndic"
    # Les documents de l'art. 2 (propres au lot d'un copropriétaire) arrivent
    # avec l'accès des copropriétaires (phase 5).
    # Hors décret, travail du conseil syndical :
    DEVIS = "devis", "Devis"
    FACTURE = "facture", "Facture"
    COURRIER = "courrier", "Courrier"
    COMPTE_RENDU_CS = "compte_rendu_cs", "Compte rendu du conseil syndical"
    PHOTO = "photo", "Photo"
    AUTRE = "autre", "Autre"


class Visibilite(models.TextChoices):
    # Les rôles de chaque niveau sont fixés dans acces.droits (seul décideur).
    CS = "cs", "Conseil syndical"
    COMPTES = "comptes", "Conseil syndical et contrôleur des comptes"
    TOUS = "tous", "Tous les comptes"


def _chemin(instance, nom):
    return f"documents/{uuid.uuid4().hex}{TYPES[instance.type_mime]}"


class Document(models.Model):
    titre = models.CharField(max_length=200)
    categorie = models.CharField(max_length=30, choices=Categorie.choices)
    visibilite = models.CharField(
        max_length=10, choices=Visibilite.choices, default=Visibilite.CS, help_text="Qui peut le lire"
    )
    batiment = models.ForeignKey(
        Batiment, null=True, blank=True, on_delete=models.PROTECT, help_text="Vide = toute la copropriété"
    )
    date_document = models.DateField(null=True, blank=True, help_text="Date portée par le document")
    fichier = models.FileField(upload_to=_chemin, editable=False)
    nom_origine = models.CharField(max_length=200, editable=False)
    type_mime = models.CharField(max_length=100, editable=False)
    taille = models.PositiveBigIntegerField(editable=False)
    empreinte = models.CharField(max_length=64, editable=False, help_text="SHA-256 du fichier")
    depose_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    depose_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-depose_le"]
        verbose_name = "document"

    def __str__(self):
        return self.titre


def empreinte_sha256(fichier):
    condensat = hashlib.sha256()
    fichier.seek(0)
    for morceau in fichier.chunks():
        condensat.update(morceau)
    fichier.seek(0)
    return condensat.hexdigest()


def volume_occupe():
    return Document.objects.aggregate(total=models.Sum("taille"))["total"] or 0

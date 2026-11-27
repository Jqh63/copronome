"""Durées de conservation des documents : un document en cours de validité ou
dans sa durée de conservation ne se retire pas (choix du CS, 2026-11-27).

Aucun texte ne fixe de durée minimale pour les archives d'un syndicat :
l'art. 33 du décret n° 67-223 dit seulement que le syndic les détient et que
leur conservation fait partie de sa mission. Les durées ci-dessous sont donc
déduites des délais pour agir (nature « déduite ») ou d'un usage (« usage »),
et chaque règle affiche sa justification. Recherche du 2026-11-27, textes
non relus un à un : à revoir avant tout usage contentieux.

Deux exceptions au blocage : une erreur de dépôt dans les 48 h, et un
effacement imposé (RGPD, décision de justice), toujours possible et journalisé.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from documents.models import Categorie

DELAI_ERREUR = timedelta(hours=48)

# Point de départ du délai.
DOCUMENT = "document"  # date portée par le document, à défaut date de dépôt
FIN = "fin"  # fin de validité ou d'effet (fin du contrat, réception des travaux)


@dataclass(frozen=True)
class Regle:
    annees: int | None  # None : sans limite ; 0 : aucune durée minimale
    depart: str
    justification: str


SANS_LIMITE = Regle(
    None, DOCUMENT, "Archive du syndicat (décret n° 67-223, art. 33) : conservée sans limite."
)
AUCUNE = Regle(0, DOCUMENT, "Aucune durée minimale.")

REGLES = {
    Categorie.REGLEMENT: SANS_LIMITE,
    Categorie.FICHE_SYNTHETIQUE: SANS_LIMITE,
    Categorie.CARNET_ENTRETIEN: SANS_LIMITE,
    Categorie.DIAGNOSTICS: Regle(
        None,
        DOCUMENT,
        "Diagnostic technique : conservé et tenu à jour (CSP, art. R1334-29-5 pour l'amiante).",
    ),
    Categorie.ASSURANCE: Regle(
        5, FIN, "Fin du contrat + 5 ans, délai pour agir (C. civ., art. 2224) — déduite."
    ),
    Categorie.CONTRATS: Regle(
        10,
        FIN,
        "Fin du contrat ou réception des travaux + 10 ans, décennale (C. civ., art. 1792-4-1) — déduite.",
    ),
    Categorie.CONTRATS_ENTRETIEN: Regle(
        5, FIN, "Fin du contrat + 5 ans, délai pour agir (C. civ., art. 2224) — déduite."
    ),
    Categorie.PV_AG: Regle(
        None, DOCUMENT, "Titre des décisions du syndicat (décret n° 67-223, art. 33) : sans limite."
    ),
    Categorie.CONTRAT_SYNDIC: Regle(
        5, FIN, "Fin du mandat + 5 ans, délai pour agir (C. civ., art. 2224) — déduite."
    ),
    Categorie.COMPTES: Regle(
        10, DOCUMENT, "10 ans après l'exercice, par analogie avec C. com., art. L123-22 — usage."
    ),
    Categorie.RELEVES_BANCAIRES: Regle(10, DOCUMENT, "10 ans, alignés sur les comptes — usage."),
    Categorie.CONTENTIEUX: Regle(None, DOCUMENT, "Décision de justice : conservée sans limite — usage."),
    # Donnée personnelle : le RGPD borne la durée par le haut, pas par le bas.
    Categorie.LISTE_COPROPRIETAIRES: Regle(
        0, DOCUMENT, "Aucune durée minimale (données personnelles, RGPD)."
    ),
    Categorie.ATTESTATIONS_SYNDIC: Regle(
        5, FIN, "Fin de validité + 5 ans, délai pour agir (C. civ., art. 2224) — déduite."
    ),
    Categorie.DEVIS: Regle(5, DOCUMENT, "5 ans, délai pour agir (C. civ., art. 2224) — usage."),
    Categorie.FACTURE: Regle(10, DOCUMENT, "10 ans, alignées sur les comptes — usage."),
    Categorie.COURRIER: Regle(5, DOCUMENT, "5 ans, délai pour agir (C. civ., art. 2224) — usage."),
    Categorie.COMPTE_RENDU_CS: Regle(
        None, DOCUMENT, "Aligné sur les procès-verbaux d'AG : sans limite — usage."
    ),
    Categorie.PHOTO: Regle(10, DOCUMENT, "10 ans, comme le dossier de travaux ou de sinistre — usage."),
    Categorie.AUTRE: AUCUNE,
}


@dataclass(frozen=True)
class Echeance:
    """Jusqu'à quand un document se conserve. `jusquau` None et `sans_limite`
    faux : la date de départ manque (fin de validité à saisir), donc conservé."""

    regle: Regle
    jusquau: date | None
    sans_limite: bool

    def conserve(self, aujourd_hui):
        if self.sans_limite or self.jusquau is None:
            return True
        return aujourd_hui < self.jusquau

    @property
    def libelle(self):
        if self.sans_limite:
            return "Sans limite"
        if self.jusquau is None:
            return "Fin de validité à saisir"
        return f"Jusqu'au {self.jusquau:%d/%m/%Y}"


def _ajouter_annees(jour, annees):
    try:
        return jour.replace(year=jour.year + annees)
    except ValueError:  # 29 février
        return jour.replace(year=jour.year + annees, day=28)


def echeance(document):
    regle = REGLES.get(document.categorie, AUCUNE)
    if regle.annees is None:
        return Echeance(regle, None, True)
    if regle.depart == FIN:
        base = document.valide_jusquau
    else:
        base = document.date_document or document.depose_le.date()
    if base is None:
        return Echeance(regle, None, False)
    return Echeance(regle, _ajouter_annees(base, regle.annees), False)


def retrait_bloque(document, maintenant):
    """Message de refus, ou None si le retrait est permis pour la raison
    « fin de conservation ». Toute la chaîne de versions compte : le retrait
    les emporte toutes."""
    aujourd_hui = maintenant.date()
    for version in (document, *document.versions_precedentes()):
        e = echeance(version)
        if e.conserve(aujourd_hui):
            return f"Ce document est conservé ({e.libelle.lower()}) : {e.regle.justification}"
    return None


def erreur_encore_possible(document, maintenant):
    return maintenant - document.depose_le < DELAI_ERREUR

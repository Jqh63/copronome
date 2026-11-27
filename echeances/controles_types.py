"""Bibliothèque de contrôles types : modèles qui pré-remplissent une échéance.

N'entre ici qu'une périodicité **lue sur une source officielle** (Légifrance
ou service-public.gouv.fr), avec la source dans `reference` (CLAUDE.md,
principes de code). Lecture du 2026-11-27 :

- DPE collectif : CCH L126-31 (version en vigueur depuis le 2026-05-28),
  « renouvelé ou mis à jour tous les dix ans » ; calendrier par nombre de lots
  sur service-public F37504.
- Projet de plan pluriannuel de travaux : loi 65-557 art. 14-2 I, « actualisé
  tous les dix ans » ; service-public F36760.
- Mandat du syndic : service-public F2608, « 3 ans maximum » (décret 67-223
  art. 28 cité par la fiche, non lu).
- Mandat du conseil syndical : service-public F2610, « au maximum 3 ans »
  (décret 67-223 art. 22 à 27 cités par la fiche, non lus).
- Amiante, liste A en surveillance périodique : service-public F742,
  « nouvelle évaluation […] dans un délai maximal de 3 ans » (CSP R1334-14 à
  R1334-29-9 cités, article précis non lu).

Écartés faute de source officielle lue : ascenseur (entretien, contrôle
technique), ramonage, portes de garage, extincteurs. Le conseil syndical les
saisit lui-même, avec son contrat ou son texte.

Un modèle ne crée rien : la date de la prochaine échéance dépend de la
copropriété (dernier diagnostic, date de l'AG) et reste saisie par le CS.
"""

from dataclasses import dataclass

from echeances.models import Echeance


@dataclass(frozen=True)
class ControleType:
    code: str
    titre: str
    type: str
    periodicite_mois: int
    reference: str
    notes: str = ""

    def initial(self):
        return {
            "titre": self.titre,
            "type": self.type,
            "periodicite_mois": self.periodicite_mois,
            "reference": self.reference,
            "notes": self.notes,
        }


CONTROLES_TYPES = (
    ControleType(
        code="dpe-collectif",
        titre="Diagnostic de performance énergétique collectif",
        type=Echeance.Type.CONTROLE,
        periodicite_mois=120,
        reference="CCH art. L126-31 ; service-public.gouv.fr F37504",
        notes=(
            "Bâtiment d'habitation collective dont le permis a été déposé avant le 2013-01-01. "
            "Pas de renouvellement si un DPE postérieur au 2021-07-01 classe le bâtiment en A, B ou C."
        ),
    ),
    ControleType(
        code="pppt",
        titre="Projet de plan pluriannuel de travaux (actualisation)",
        type=Echeance.Type.TRAVAUX,
        periodicite_mois=120,
        reference="Loi 65-557 art. 14-2 I ; service-public.gouv.fr F36760",
        notes=(
            "Immeuble à destination d'habitation, réception des travaux de construction "
            "il y a plus de 15 ans. "
            "Dispense si un diagnostic technique global ne prévoit aucun travaux sur les dix ans suivants."
        ),
    ),
    ControleType(
        code="mandat-syndic",
        titre="Fin du mandat du syndic",
        type=Echeance.Type.MANDAT,
        periodicite_mois=36,
        reference="service-public.gouv.fr F2608 (décret 67-223 art. 28)",
        notes="Durée maximale ; saisir la durée votée en AG si elle est plus courte.",
    ),
    ControleType(
        code="mandat-cs",
        titre="Fin du mandat des membres du conseil syndical",
        type=Echeance.Type.MANDAT,
        periodicite_mois=36,
        reference="service-public.gouv.fr F2610 (décret 67-223 art. 22 à 27)",
        notes="Durée maximale ; le règlement de copropriété ou l'AG peut fixer une durée plus courte.",
    ),
    ControleType(
        code="amiante-liste-a",
        titre="Amiante : nouvelle évaluation des matériaux de la liste A",
        type=Echeance.Type.CONTROLE,
        periodicite_mois=36,
        reference="service-public.gouv.fr F742 (CSP art. R1334-14 à R1334-29-9)",
        notes=(
            "Seulement si le dossier technique amiante classe des matériaux de la liste A "
            "en surveillance périodique. Aucune périodicité fixée pour la liste B."
        ),
    ),
)

PAR_CODE = {controle.code: controle for controle in CONTROLES_TYPES}

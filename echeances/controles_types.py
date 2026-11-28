"""Bibliothèque de contrôles types : modèles qui pré-remplissent une échéance.

N'entre ici qu'une périodicité **lue sur une source officielle** (Légifrance
ou service-public.gouv.fr), avec la source dans `reference` (CLAUDE.md,
principes de code). Lecture du 2026-11-27 ; textes du décret 67-223, du CSP
R1334-27 et du CCH R134-11 lus le 2026-11-28 par l'API Légifrance (PISTE,
bac à sable, base du 2026-11-26) :

- DPE collectif : CCH L126-31 (version en vigueur depuis le 2026-05-28),
  « renouvelé ou mis à jour tous les dix ans » ; calendrier par nombre de lots
  sur service-public F37504.
- Projet de plan pluriannuel de travaux : loi 65-557 art. 14-2 I, « actualisé
  tous les dix ans » ; service-public F36760.
- Mandat du syndic : décret 67-223 art. 28 (version en vigueur depuis le
  2020-07-04), « la durée des fonctions du syndic ne peut excéder trois
  années » ; une année au plus pendant le délai décennal si le syndic ou un
  proche a participé à la construction ; service-public F2608.
- Mandat du conseil syndical : décret 67-223 art. 22 (en vigueur depuis le
  2004-09-01), « ne peut excéder trois années renouvelables » ;
  service-public F2610.
- Amiante, liste A : CSP R1334-27 1° (en vigueur depuis le 2012-02-01),
  évaluation périodique « dans un délai maximal de trois ans » à compter du
  rapport de repérage ou de la dernière évaluation, ou à toute modification
  substantielle de l'ouvrage ; service-public F742.

- Ascenseur, contrôle technique : CCH R134-11 (en vigueur depuis le
  2026-05-15), « tous les cinq ans » ; service-public F10538. La visite d'entretien toutes les 6 semaines relève du contrat
  de l'ascensoriste, pas d'une échéance du CS.
- Ramonage : CSP R1331-71 (en vigueur depuis le 2023-10-01, lu sur
  Légifrance), « au moins tous les douze mois » ; appareils collectifs « au
  moins tous les six mois, dont une fois pendant la période de chauffe » ; un
  arrêté local peut en imposer plus.

Écartés faute de source officielle lue : portes de garage, extincteurs. Le
conseil syndical les saisit lui-même, avec son contrat ou son texte.

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
        reference="Décret 67-223 art. 28 ; service-public.gouv.fr F2608",
        notes=(
            "Durée maximale ; saisir la durée votée en AG si elle est plus courte. "
            "Un an au plus pendant les dix ans suivant la réception si le syndic a participé à la construction."
        ),
    ),
    ControleType(
        code="mandat-cs",
        titre="Fin du mandat des membres du conseil syndical",
        type=Echeance.Type.MANDAT,
        periodicite_mois=36,
        reference="Décret 67-223 art. 22 ; service-public.gouv.fr F2610",
        notes="Durée maximale ; le règlement de copropriété ou l'AG peut fixer une durée plus courte.",
    ),
    ControleType(
        code="amiante-liste-a",
        titre="Amiante : nouvelle évaluation des matériaux de la liste A",
        type=Echeance.Type.CONTROLE,
        periodicite_mois=36,
        reference="CSP art. R1334-27 ; service-public.gouv.fr F742",
        notes=(
            "Seulement si le dossier technique amiante classe des matériaux de la liste A "
            "en surveillance périodique. Aucune périodicité fixée pour la liste B."
        ),
    ),
    ControleType(
        code="ascenseur-controle-technique",
        titre="Ascenseur : contrôle technique",
        type=Echeance.Type.CONTROLE,
        periodicite_mois=60,
        reference="CCH art. R134-11 ; service-public.gouv.fr F10538",
        notes=(
            "Une échéance par ascenseur. Prévenir les occupants par affichage sur la porte "
            "quelques jours avant le contrôle."
        ),
    ),
    ControleType(
        code="ramonage",
        titre="Ramonage des conduits de fumée",
        type=Echeance.Type.CONTROLE,
        periodicite_mois=12,
        reference="CSP art. R1331-71",
        notes=(
            "Conduits et tuyaux de raccordement des appareils individuels. "
            "Un arrêté local peut imposer plusieurs ramonages par an, dont un pendant la période de chauffe."
        ),
    ),
    ControleType(
        code="ramonage-collectif",
        titre="Ramonage des conduits d'appareils collectifs",
        type=Echeance.Type.CONTROLE,
        periodicite_mois=6,
        reference="CSP art. R1331-71",
        notes=(
            "Dont une fois pendant la période de chauffe. Tous les douze mois si l'appareil "
            "ne brûle que du gaz et que le conduit n'a jamais servi à un combustible solide "
            "ou liquide (ou a été ramoné avant le changement)."
        ),
    ),
)

PAR_CODE = {controle.code: controle for controle in CONTROLES_TYPES}

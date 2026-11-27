"""Purge des coordonnées des anciens copropriétaires et occupants.

Règle (choisie par le conseil syndical, responsable de traitement ; la CNIL
ne fixe pas de durée pour la copropriété) : une personne reste dans la liste
tant qu'elle détient ou occupe un lot ; après la fin de son dernier lien,
ses coordonnées sont gardées DUREE_ANS ans, puis effacées.

Durée : délai de prescription des actions personnelles entre un
copropriétaire et le syndicat (recouvrement de charges impayées). Loi
n° 65-557 du 10 juillet 1965, art. 42, al. 1, en vigueur depuis le
01/06/2020 (ordonnance n° 2019-1101, art. 37) : l'article 2224 du code civil
s'applique, soit cinq ans à compter du jour où le titulaire a connu les faits.
Lu sur Légifrance le 2026-11-27.

L'effacement anonymise la fiche au lieu de la supprimer : l'historique des
lots (qui a détenu quoi, quand) garde ses dates, sans nom ni coordonnées.
Une personne liée à un compte actif n'est jamais effacée (signalée à part).
"""

from django.db import transaction
from django.utils import timezone

from audit.models import Action, journaliser
from copro.models import Personne

DUREE_ANS = 5


def _ajouter_ans(date, ans):
    try:
        return date.replace(year=date.year + ans)
    except ValueError:  # 29 février
        return date.replace(year=date.year + ans, day=28)


def fin_du_dernier_lien(personne, aujourdhui):
    """Date de fin du dernier lien (détention ou occupation), ou None si la
    personne a un lien en cours ou n'en a jamais eu."""
    fins = []
    for lien in [*personne.detentions.all(), *personne.occupations.all()]:
        if lien.fin is None or lien.fin >= aujourdhui:
            return None
        fins.append(lien.fin)
    return max(fins, default=None)


def a_compte_actif(personne):
    return personne.affectation_set.filter(utilisateur__is_active=True).exists()


def candidates(aujourdhui=None):
    """(à effacer, gardées car liées à un compte actif) : listes de
    (personne, fin du dernier lien)."""
    aujourdhui = aujourdhui or timezone.localdate()
    a_effacer, bloquees = [], []
    personnes = Personne.objects.filter(efface_le__isnull=True).prefetch_related("detentions", "occupations")
    for personne in personnes:
        fin = fin_du_dernier_lien(personne, aujourdhui)
        if fin is None or _ajouter_ans(fin, DUREE_ANS) > aujourdhui:
            continue
        (bloquees if a_compte_actif(personne) else a_effacer).append((personne, fin))
    return a_effacer, bloquees


@transaction.atomic
def effacer(personne, fin, aujourdhui):
    personne.nom = "Personne effacée"
    personne.prenom = ""
    personne.email = ""
    personne.telephone = ""
    personne.adresse_postale = ""
    personne.notes = ""
    personne.efface_le = aujourdhui
    personne.save()
    # Journalisée après l'effacement : le journal, en ajout seul, ne doit
    # jamais recevoir le nom effacé.
    journaliser(
        Action.PERSONNE_EFFACEE,
        objet=personne,
        fin_du_dernier_lien=fin.isoformat(),
        duree_ans=DUREE_ANS,
    )


def purger(aujourdhui=None, appliquer=False):
    aujourdhui = aujourdhui or timezone.localdate()
    a_effacer, bloquees = candidates(aujourdhui)
    if appliquer:
        for personne, fin in a_effacer:
            effacer(personne, fin, aujourdhui)
    return a_effacer, bloquees

"""Efface les coordonnées des personnes sans lien avec un lot depuis plus de
DUREE_ANS ans (règle et source : copro.purge). Sans --appliquer, n'affiche
que le décompte. N'affiche jamais un nom : numéros de fiche seulement."""

from django.core.management.base import BaseCommand

from copro.purge import DUREE_ANS, purger


class Command(BaseCommand):
    help = "Purge des coordonnées des anciens copropriétaires et occupants"

    def add_arguments(self, parser):
        parser.add_argument("--appliquer", action="store_true", help="Effacer (sinon : décompte seul)")

    def handle(self, *args, appliquer=False, **options):
        a_effacer, bloquees = purger(appliquer=appliquer)
        verbe = "effacée(s)" if appliquer else "à effacer (relancer avec --appliquer)"
        self.stdout.write(f"purge ({DUREE_ANS} ans) : {len(a_effacer)} personne(s) {verbe}")
        for personne, fin in bloquees:
            self.stdout.write(
                f"  gardée : fiche n° {personne.pk}, dernier lien terminé le {fin:%d/%m/%Y}, "
                "liée à un compte actif (désactiver le compte pour permettre la purge)"
            )

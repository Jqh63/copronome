"""Saisit ou met à jour l'identité de l'instance (enregistrement unique).

manage.py copropriete --nom "Les Tilleuls" --commune "Exempleville" --code-insee 99999
          [--adresse "..."] [--immatriculation "..."]
Sans argument : affiche l'identité actuelle. Rejouable : la même commande ne
crée jamais un second enregistrement (contrat de branchement, création idempotente).
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from copro.models import Copropriete

CHAMPS = ("nom", "commune", "code_insee", "adresse", "immatriculation")


class Command(BaseCommand):
    help = "Saisit ou affiche l'identité de la copropriété de l'instance."

    def add_arguments(self, parser):
        for champ in CHAMPS:
            parser.add_argument("--" + champ.replace("_", "-"), dest=champ)

    def handle(self, *args, **options):
        valeurs = {c: options[c] for c in CHAMPS if options.get(c) is not None}
        copropriete = Copropriete.courante()
        if not valeurs:
            if copropriete is None:
                raise CommandError("Identité non saisie : passer --nom, --commune et --code-insee.")
            for champ in CHAMPS:
                self.stdout.write(f"{champ} : {getattr(copropriete, champ)}")
            return
        copropriete = copropriete or Copropriete()
        for champ, valeur in valeurs.items():
            setattr(copropriete, champ, valeur.strip())
        try:
            copropriete.full_clean(validate_unique=False)
        except ValidationError as erreur:
            details = "; ".join(f"{c} : {' '.join(m)}" for c, m in erreur.message_dict.items())
            raise CommandError(details) from erreur
        copropriete.save()
        self.stdout.write(self.style.SUCCESS(f"Copropriété : {copropriete}"))

"""Charge une copropriété de démonstration entièrement fictive.

Refuse si la base contient déjà des lots : ne mélange jamais démo et
données réelles. Noms en « Exemple »/« Démo », mails en example.org,
téléphones en 00 00 00 00 (motifs autorisés par .gitleaks.toml).
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from copro.models import (
    Batiment,
    CleRepartition,
    Detention,
    Lot,
    Occupation,
    PartieCommune,
    Personne,
    Tantieme,
)

BATIMENTS = ["A", "B", "C"]
LOTS_PAR_BATIMENT = 4  # 3 logements + 1 parking
DEBUT = datetime.date(2020, 1, 1)


class Command(BaseCommand):
    help = "Charge une copropriété de démonstration fictive (base vide uniquement)."

    @transaction.atomic
    def handle(self, *args, **options):
        if Lot.objects.exists():
            raise CommandError("La base contient déjà des lots : démonstration refusée.")

        generales = CleRepartition.objects.create(nom="Charges générales", base=10000)
        parking = CleRepartition.objects.create(nom="Parking", base=1000)
        lots = []
        for ordre, lettre in enumerate(BATIMENTS):
            batiment = Batiment.objects.create(nom=f"Bâtiment {lettre}", ordre=ordre)
            escalier = PartieCommune.objects.create(
                nom=f"Escalier {lettre}", type=PartieCommune.Type.ESCALIER, batiment=batiment
            )
            PartieCommune.objects.create(
                nom=f"Ascenseur {lettre}", type=PartieCommune.Type.ASCENSEUR, batiment=batiment
            )
            cle_batiment = CleRepartition.objects.create(nom=f"Bâtiment {lettre}", base=1000)
            for etage in range(3):
                lot = Lot.objects.create(
                    numero=f"{lettre}{etage + 1:02d}",
                    type=Lot.Type.LOGEMENT,
                    batiment=batiment,
                    etage=etage,
                    escalier=escalier,
                )
                Tantieme.objects.create(
                    lot=lot, cle=cle_batiment, valeur=1000 // 3 + (1 if etage == 0 else 0)
                )
                lots.append(lot)
            lot_parking = Lot.objects.create(
                numero=f"{lettre}P1", type=Lot.Type.PARKING, batiment=batiment, etage=-1
            )
            Tantieme.objects.create(
                lot=lot_parking, cle=parking, valeur=1000 // len(BATIMENTS) + (1 if ordre == 0 else 0)
            )
            lots.append(lot_parking)

        PartieCommune.objects.create(nom="Espaces verts", type=PartieCommune.Type.ESPACE_VERT)
        part = 10000 // len(lots)
        for i, lot in enumerate(lots):
            Tantieme.objects.create(
                lot=lot, cle=generales, valeur=part + (10000 - part * len(lots) if i == 0 else 0)
            )

        for i, lot in enumerate(lots, start=1):
            personne = Personne.objects.create(
                nom="Exemple",
                prenom=f"Copropriétaire {i:02d}",
                email=f"copro{i:02d}@example.org",
                telephone="06 00 00 00 00",
            )
            Detention.objects.create(personne=personne, lot=lot, debut=DEBUT)

        indivisaire = Personne.objects.create(
            nom="Démo", prenom="Indivisaire", email="indivision@example.org"
        )
        Detention.objects.create(
            personne=indivisaire,
            lot=lots[0],
            nature=Detention.Nature.INDIVISION,
            quote_part_numerateur=1,
            quote_part_denominateur=2,
            debut=DEBUT,
        )
        Detention.objects.filter(lot=lots[0], personne__nom="Exemple").update(
            nature=Detention.Nature.INDIVISION, quote_part_denominateur=2
        )
        societe = Personne.objects.create(type=Personne.Type.MORALE, nom="SCI Démo", email="sci@example.org")
        Detention.objects.filter(lot=lots[1]).update(fin=datetime.date(2024, 6, 30))
        Detention.objects.create(personne=societe, lot=lots[1], debut=datetime.date(2024, 7, 1))
        locataire = Personne.objects.create(nom="Démo", prenom="Locataire", email="locataire@example.org")
        Occupation.objects.create(personne=locataire, lot=lots[2], debut=datetime.date(2023, 9, 1))

        self.stdout.write(
            self.style.SUCCESS(
                f"Démonstration chargée : {len(lots)} lots, {Personne.objects.count()} personnes."
            )
        )

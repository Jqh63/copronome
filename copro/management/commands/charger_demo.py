"""Charge une copropriété de démonstration entièrement fictive.

Structure réaliste d'une petite résidence : 3 bâtiments, 32 lots
(logements, caves, parkings), clés générale, bâtiment, escalier,
ascenseur, stationnements, portail et chaudières. Aucun nom, adresse ni
chiffre repris d'une copropriété réelle : noms en « Exemple »/« Démo »,
mails en example.org, téléphones en 00 00 00 00 (motifs autorisés par
.gitleaks.toml).

`--activite` ajoute échéances, incidents et rendez-vous datés autour du
jour du chargement. Refuse si la base contient déjà des lots : ne mélange
jamais démo et données réelles.
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from agenda.models import Evenement as RendezVous
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
from echeances.models import Echeance, realiser
from incidents.models import Evenement, Incident, Statut, journaliser

DEBUT = datetime.date(2015, 1, 1)

# Par bâtiment : logements (étage, typologie), caves, parkings, logements sans chaudière.
BATIMENTS = {
    "A": {
        "logements": [(0, "T2"), (0, "T3"), (1, "T3"), (1, "T4"), (2, "T3"), (2, "T4"), (3, "T5")],
        "caves": 2,
        "parkings": 0,
        "sans_chaudiere": {1},
    },
    "B": {
        "logements": [(0, "T2"), (0, "T2"), (1, "T3"), (1, "T3"), (2, "T3"), (2, "T4"), (3, "T4"), (3, "T4")],
        "caves": 0,
        "parkings": 6,
        "sans_chaudiere": set(),
    },
    "C": {
        "logements": [(0, "T3"), (1, "T2"), (1, "T4"), (2, "T3"), (2, "T4"), (3, "T5")],
        "caves": 3,
        "parkings": 0,
        "sans_chaudiere": {4},
    },
}
POIDS_TYPOLOGIE = {"T2": 45, "T3": 65, "T4": 80, "T5": 95}  # surface pondérée fictive
POIDS_CAVE, POIDS_PARKING = 3, 8


def repartir(cle, poids):
    """Attribue `cle.base` tantièmes au prorata de `poids` {lot: poids},
    au plus fort reste : la somme tombe exactement sur la base."""
    total = sum(poids.values())
    bruts = {lot: cle.base * p / total for lot, p in poids.items()}
    valeurs = {lot: int(v) for lot, v in bruts.items()}
    reste = cle.base - sum(valeurs.values())
    for lot in sorted(bruts, key=lambda lot: bruts[lot] - valeurs[lot], reverse=True)[:reste]:
        valeurs[lot] += 1
    Tantieme.objects.bulk_create(Tantieme(lot=lot, cle=cle, valeur=v) for lot, v in valeurs.items())


class Command(BaseCommand):
    help = "Charge une copropriété de démonstration fictive (base vide uniquement)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--activite", action="store_true", help="Ajoute échéances, incidents et rendez-vous."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if Lot.objects.exists():
            raise CommandError("La base contient déjà des lots : démonstration refusée.")

        lots = self._structure()
        self._personnes(lots)
        message = f"Démonstration chargée : {len(lots)} lots, {Personne.objects.count()} personnes"
        if options["activite"]:
            self._activite()
            message += (
                f", {Echeance.objects.count()} échéances, {Incident.objects.count()} incidents,"
                f" {RendezVous.objects.count()} rendez-vous"
            )
        self.stdout.write(self.style.SUCCESS(message + "."))

    def _structure(self):
        poids_general, poids_portail, poids_chaudiere, poids_stationnement = {}, {}, {}, {}
        lots = []
        for ordre, (lettre, spec) in enumerate(BATIMENTS.items()):
            batiment = Batiment.objects.create(nom=f"Bâtiment {lettre}", ordre=ordre)
            escalier = PartieCommune.objects.create(
                nom=f"Escalier {lettre}", type=PartieCommune.Type.ESCALIER, batiment=batiment
            )
            PartieCommune.objects.create(
                nom=f"Ascenseur {lettre}", type=PartieCommune.Type.ASCENSEUR, batiment=batiment
            )
            PartieCommune.objects.create(
                nom=f"Hall {lettre}", type=PartieCommune.Type.HALL, batiment=batiment
            )
            poids_batiment, poids_escalier, poids_ascenseur = {}, {}, {}
            for n, (etage, typologie) in enumerate(spec["logements"], start=1):
                lot = Lot.objects.create(
                    numero=f"{lettre}{n:02d}",
                    type=Lot.Type.LOGEMENT,
                    batiment=batiment,
                    etage=etage,
                    escalier=escalier,
                    description=typologie,
                )
                poids = POIDS_TYPOLOGIE[typologie]
                poids_batiment[lot] = poids_escalier[lot] = poids
                # Le rez-de-chaussée ne se sert pas de l'ascenseur ; plus on monte, plus on paie.
                if etage > 0:
                    poids_ascenseur[lot] = poids * (1 + etage / 2)
                poids_portail[lot] = 1
                if n not in spec["sans_chaudiere"]:
                    poids_chaudiere[lot] = 1
                lots.append(lot)
            if spec["caves"]:
                PartieCommune.objects.create(
                    nom=f"Caves {lettre}", type=PartieCommune.Type.CAVES, batiment=batiment
                )
            for n in range(1, spec["caves"] + 1):
                lot = Lot.objects.create(
                    numero=f"{lettre}-cave{n}", type=Lot.Type.CAVE, batiment=batiment, etage=-1
                )
                poids_batiment[lot] = POIDS_CAVE
                lots.append(lot)
            if spec["parkings"]:
                PartieCommune.objects.create(
                    nom=f"Parking {lettre}", type=PartieCommune.Type.PARKING, batiment=batiment
                )
            for n in range(1, spec["parkings"] + 1):
                lot = Lot.objects.create(
                    numero=f"{lettre}-park{n}", type=Lot.Type.PARKING, batiment=batiment, etage=-1
                )
                poids_batiment[lot] = POIDS_PARKING
                poids_portail[lot] = poids_stationnement[lot] = 1
                lots.append(lot)
            poids_general.update(poids_batiment)
            for nom, poids in (
                (f"Bâtiment {lettre}", poids_batiment),
                (f"Escalier {lettre}", poids_escalier),
                (f"Ascenseur {lettre}", poids_ascenseur),
            ):
                repartir(CleRepartition.objects.create(nom=nom, base=1000), poids)

        PartieCommune.objects.create(nom="Espaces verts", type=PartieCommune.Type.ESPACE_VERT)
        PartieCommune.objects.create(nom="Portail", type=PartieCommune.Type.AUTRE)
        repartir(CleRepartition.objects.create(nom="Charges générales", base=10000), poids_general)
        for nom, poids, description in (
            ("Portail", poids_portail, "Une part par logement et par parking."),
            ("Chaudières", poids_chaudiere, "Une part par logement équipé d'une chaudière."),
            ("Stationnements B", poids_stationnement, "Une part par place du parking B."),
        ):
            repartir(CleRepartition.objects.create(nom=nom, base=len(poids), description=description), poids)
        return lots

    def _personnes(self, lots):
        """Un propriétaire par logement ; caves et parkings détenus par des
        propriétaires de logements du même bâtiment ; quelques cas
        particuliers (indivision, SCI, vente, locataires)."""
        proprietaires = {}
        for i, lot in enumerate((lot for lot in lots if lot.type == Lot.Type.LOGEMENT), start=1):
            personne = Personne.objects.create(
                nom="Exemple",
                prenom=f"Copropriétaire {i:02d}",
                email=f"copro{i:02d}@example.org",
                telephone="06 00 00 00 00",
            )
            Detention.objects.create(personne=personne, lot=lot, debut=DEBUT)
            proprietaires.setdefault(lot.batiment_id, []).append(personne)
        annexes = {}  # rang de la cave ou du parking dans son bâtiment
        for lot in lots:
            if lot.type != Lot.Type.LOGEMENT:
                du_batiment = proprietaires[lot.batiment_id]
                rang = annexes.get(lot.batiment_id, 0)
                annexes[lot.batiment_id] = rang + 1
                Detention.objects.create(personne=du_batiment[rang % len(du_batiment)], lot=lot, debut=DEBUT)

        logements = [lot for lot in lots if lot.type == Lot.Type.LOGEMENT]
        indivisaire = Personne.objects.create(
            nom="Démo", prenom="Indivisaire", email="indivision@example.org"
        )
        Detention.objects.filter(lot=logements[0]).update(
            nature=Detention.Nature.INDIVISION, quote_part_denominateur=2
        )
        Detention.objects.create(
            personne=indivisaire,
            lot=logements[0],
            nature=Detention.Nature.INDIVISION,
            quote_part_numerateur=1,
            quote_part_denominateur=2,
            debut=DEBUT,
        )
        societe = Personne.objects.create(type=Personne.Type.MORALE, nom="SCI Démo", email="sci@example.org")
        Detention.objects.filter(lot=logements[1]).update(fin=datetime.date(2024, 6, 30))
        Detention.objects.create(personne=societe, lot=logements[1], debut=datetime.date(2024, 7, 1))
        for n, lot in enumerate(logements[2::4], start=1):
            locataire = Personne.objects.create(
                nom="Démo", prenom=f"Locataire {n:02d}", email=f"locataire{n:02d}@example.org"
            )
            Occupation.objects.create(personne=locataire, lot=lot, debut=datetime.date(2023, 9, 1))

    def _activite(self):
        aujourdhui = timezone.localdate()

        def jours(n):
            return aujourdhui + datetime.timedelta(days=n)

        ascenseurs = PartieCommune.objects.filter(type=PartieCommune.Type.ASCENSEUR)
        for ascenseur in ascenseurs:
            Echeance.objects.create(
                titre=f"Contrôle technique — {ascenseur.nom}",
                type=Echeance.Type.CONTROLE,
                prochaine_le=jours(120 + 90 * ascenseur.batiment.ordre),
                periodicite_mois=60,
                rappel_jours=90,
                reference="Code de la construction et de l'habitation, art. R134-11",
                partie_commune=ascenseur,
                batiment=ascenseur.batiment,
            )
        for titre, type, dans, periodicite, rappel in (
            ("Assemblée générale annuelle", Echeance.Type.AG, 160, 12, 60),
            ("Échéance du contrat d'assurance de l'immeuble", Echeance.Type.ASSURANCE, 75, 12, 60),
            ("Fin du mandat du syndic", Echeance.Type.MANDAT, 250, None, 120),
            ("Vérification des extincteurs", Echeance.Type.CONTROLE, -5, 12, 30),
            ("Contrat d'entretien des espaces verts", Echeance.Type.CONTRAT, 40, 12, 60),
        ):
            Echeance.objects.create(
                titre=titre,
                type=type,
                prochaine_le=jours(dans),
                periodicite_mois=periodicite,
                rappel_jours=rappel,
            )
        realiser(
            Echeance.objects.get(titre="Vérification des extincteurs"),
            jours(-3),
            None,
            note="Deux extincteurs remplacés (démo).",
        )

        hall_b = PartieCommune.objects.get(nom="Hall B")
        for titre, description, priorite, localisation, suite in (
            (
                "Porte du hall B qui ne ferme plus",
                "La ventouse ne retient plus la porte.",
                Incident.Priorite.HAUTE,
                {"partie_commune": hall_b},
                [Evenement.Type.TRANSMISSION],
            ),
            (
                "Infiltration au plafond",
                "Tache d'humidité qui s'étend au plafond de la chambre.",
                Incident.Priorite.URGENTE,
                {"lot": Lot.objects.get(numero="C06")},
                [Evenement.Type.TRANSMISSION, Evenement.Type.REPONSE_SYNDIC],
            ),
            (
                "Éclairage du parking B en panne",
                "Trois néons hors service.",
                Incident.Priorite.NORMALE,
                {"partie_commune": PartieCommune.objects.get(nom="Parking B")},
                [],
            ),
            ("Haie à tailler côté rue", "", Incident.Priorite.BASSE, {}, [Evenement.Type.STATUT]),
        ):
            incident = Incident(
                titre=titre, description=description or titre, priorite=priorite, **localisation
            )
            incident.full_clean()
            incident.save()
            journaliser(incident, Evenement.Type.CREATION, None)
            for type in suite:
                if type == Evenement.Type.STATUT:
                    journaliser(
                        incident,
                        type,
                        None,
                        texte="Fait par le jardinier (démo).",
                        nouveau_statut=Statut.RESOLU,
                    )
                elif type == Evenement.Type.REPONSE_SYNDIC:
                    journaliser(incident, type, None, texte="Couvreur missionné (démo).")
                else:
                    journaliser(incident, type, None)

        maintenant = timezone.localtime().replace(minute=0, second=0, microsecond=0)
        for titre, dans, heure, lieu, batiment in (
            ("Réunion du conseil syndical", 10, 19, "Salle commune", None),
            ("Passage du couvreur", 4, 9, "", Batiment.objects.get(nom="Bâtiment C")),
            ("Assemblée générale", 160, 18, "Salle municipale", None),
        ):
            debut = (maintenant + datetime.timedelta(days=dans)).replace(hour=heure)
            RendezVous.objects.create(
                titre=titre,
                debut=debut,
                fin=debut + datetime.timedelta(hours=2),
                lieu=lieu,
                batiment=batiment,
            )

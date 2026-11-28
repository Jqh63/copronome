"""L'inventaire des licences (LICENCES-DEPENDANCES.md) suit requirements.txt :
tout paquet épinglé y figure avec sa version exacte."""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _epingles():
    for ligne in (RACINE / "requirements.txt").read_text().splitlines():
        trouve = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==(\S+)", ligne)
        if trouve:
            yield trouve.group(1).lower(), trouve.group(2)


def test_chaque_paquet_epingle_est_inventorie():
    inventaire = {
        (m.group(1).lower(), m.group(2))
        for m in re.finditer(
            r"^\| ([A-Za-z0-9_.-]+) \| ([^ |]+) \|", (RACINE / "LICENCES-DEPENDANCES.md").read_text(), re.M
        )
    }
    epingles = set(_epingles())
    assert epingles, "contrôle positif : requirements.txt lu"
    assert epingles - inventaire == set()

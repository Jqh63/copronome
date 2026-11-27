from django.shortcuts import render

from acces.droits import LIRE, batiments_visibles, exige
from copro.models import Lot


@exige(LIRE, "structure")
def liste_lots(request):
    lots = Lot.objects.select_related("batiment").prefetch_related("tantiemes__cle")
    visibles = batiments_visibles(request.user, LIRE, "structure")
    if visibles is not None:
        lots = lots.filter(batiment_id__in=visibles)
    return render(request, "copro/lots.html", {"lots": lots})

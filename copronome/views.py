from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from acces.droits import public


@public
def accueil(request):
    return render(request, "accueil.html")


@public
def sante(request):
    """Sonde de supervision : 200 si la base répond, 503 sinon."""
    try:
        with connection.cursor() as curseur:
            curseur.execute("SELECT 1")
    except Exception:
        return JsonResponse({"etat": "base injoignable"}, status=503)
    return JsonResponse({"etat": "ok"})

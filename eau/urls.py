from django.urls import path

from eau import views

app_name = "eau"
urlpatterns = [
    path("", views.liste, name="liste"),
    path("compteur/nouveau/", views.creer_compteur, name="creer_compteur"),
    path("compteur/<int:pk>/", views.compteur, name="compteur"),
    path("compteur/<int:pk>/releve/", views.ajouter_releve, name="ajouter_releve"),
    path("compteur/<int:pk>/deposer/", views.deposer, name="deposer"),
    path("tournee/<int:batiment>/", views.tournee, name="tournee"),
    path("export/", views.exporter, name="exporter"),
]

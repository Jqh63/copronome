from django.urls import path

from incidents import views

app_name = "incidents"
urlpatterns = [
    path("", views.liste, name="liste"),
    path("nouveau/", views.creer, name="creer"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/journal/", views.ajouter_evenement, name="ajouter_evenement"),
]

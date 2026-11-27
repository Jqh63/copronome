from django.urls import path

from echeances import views

app_name = "echeances"
urlpatterns = [
    path("", views.liste, name="liste"),
    path("nouvelle/", views.creer, name="creer"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/realisation/", views.realiser_echeance, name="realiser"),
]

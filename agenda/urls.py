from django.urls import path

from agenda import views

app_name = "agenda"
urlpatterns = [
    path("", views.liste, name="liste"),
    path("nouveau/", views.creer, name="creer"),
    path("<int:pk>/", views.modifier, name="modifier"),
    path("lien-ical/", views.lien_ical, name="lien_ical"),
    path("ical/<str:jeton>/", views.flux_ical, name="ical"),
]

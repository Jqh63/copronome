from django.urls import path

from documents import views

app_name = "documents"
urlpatterns = [
    path("", views.liste, name="liste"),
    path("deposer/", views.deposer, name="deposer"),
    path("<int:pk>/fichier/", views.telecharger, name="telecharger"),
]

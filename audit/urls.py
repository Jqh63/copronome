from django.urls import path

from audit import views

app_name = "audit"
urlpatterns = [
    path("", views.journal, name="journal"),
    path("export.csv", views.exporter, name="exporter"),
]

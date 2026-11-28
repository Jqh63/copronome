from allauth.account.decorators import secure_admin_login
from django.contrib import admin
from django.urls import include, path

from copro import views as copro_views
from copronome import views

# La connexion à l'admin passe par allauth (second facteur compris).
admin.site.login = secure_admin_login(admin.site.login)

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("sante/", views.sante, name="sante"),
    path("mots/", views.mots, name="mots"),
    path("lots/", copro_views.liste_lots, name="lots"),
    path("incidents/", include("incidents.urls")),
    path("documents/", include("documents.urls")),
    path("echeances/", include("echeances.urls")),
    path("eau/", include("eau.urls")),
    path("agenda/", include("agenda.urls")),
    path("journal/", include("audit.urls")),
    path("invitation/", include("acces.urls")),
    path("compte/", include("allauth.urls")),
    path("admin/", admin.site.urls),
]

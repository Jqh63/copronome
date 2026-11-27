from django.contrib import admin

from agenda.models import Evenement, JetonAgenda


@admin.register(Evenement)
class EvenementAdmin(admin.ModelAdmin):
    list_display = ["titre", "debut", "lieu", "batiment", "annule"]
    list_filter = ["annule", "batiment"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JetonAgenda)
class JetonAgendaAdmin(admin.ModelAdmin):
    """Révocation d'un lien iCal par l'admin technique (compte perdu, départ)."""

    list_display = ["utilisateur", "cree_le"]
    readonly_fields = ["utilisateur", "cree_le"]
    exclude = ["empreinte_jeton"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

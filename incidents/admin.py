from django.contrib import admin

from incidents.models import Evenement, Incident


class EvenementInline(admin.TabularInline):
    model = Evenement
    extra = 0
    can_delete = False
    readonly_fields = ["type", "texte", "nouveau_statut", "auteur", "cree_le"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    """Consultation seule : un incident vit par l'interface et son journal."""

    list_display = ["titre", "statut", "priorite", "batiment", "cree_le"]
    list_filter = ["statut", "priorite", "batiment"]
    inlines = [EvenementInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

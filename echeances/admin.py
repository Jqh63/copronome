from django.contrib import admin

from echeances.models import Echeance, Realisation


class RealisationInline(admin.TabularInline):
    model = Realisation
    extra = 0
    can_delete = False
    readonly_fields = ["realisee_le", "pour_echeance_du", "note", "auteur", "cree_le"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Echeance)
class EcheanceAdmin(admin.ModelAdmin):
    """Consultation seule : une échéance vit par l'interface et ses réalisations."""

    list_display = ["titre", "type", "prochaine_le", "periodicite_mois", "active", "batiment"]
    list_filter = ["type", "active", "batiment"]
    inlines = [RealisationInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

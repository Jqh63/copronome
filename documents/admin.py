from django.contrib import admin

from documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Consultation seule : un document se dépose par l'interface, qui vérifie
    le contenu, la taille et le quota."""

    list_display = ["titre", "categorie", "visibilite", "batiment", "taille", "depose_le"]
    list_filter = ["categorie", "visibilite", "batiment"]
    readonly_fields = ["nom_origine", "type_mime", "taille", "empreinte", "depose_par", "depose_le"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

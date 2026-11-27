from django.contrib import admin

from acces.models import Affectation, Invitation


@admin.register(Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display = ["utilisateur", "role", "batiment", "cree_le"]
    list_filter = ["role", "batiment"]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    """Lecture seule : une invitation se crée par `manage.py inviter`, qui
    seul connaît le jeton en clair."""

    list_display = ["email", "role", "batiment", "creee_le", "expire_le", "utilisee_le"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

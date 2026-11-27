"""Admin des données de référence (structure, tantièmes, personnes).

L'admin sert à la saisie initiale ; en production il sera limité aux
données de référence derrière le contrôle d'accès (ADR, § 5).
"""

from django.contrib import admin

from copro.models import (
    Batiment,
    CleRepartition,
    Detention,
    Lot,
    Occupation,
    PartieCommune,
    Personne,
    Tantieme,
)


class TantiemeInline(admin.TabularInline):
    model = Tantieme
    extra = 0


class DetentionInline(admin.TabularInline):
    model = Detention
    extra = 0
    autocomplete_fields = ["personne"]


class OccupationInline(admin.TabularInline):
    model = Occupation
    extra = 0
    autocomplete_fields = ["personne"]


@admin.register(Batiment)
class BatimentAdmin(admin.ModelAdmin):
    list_display = ["nom", "ordre"]


@admin.register(PartieCommune)
class PartieCommuneAdmin(admin.ModelAdmin):
    list_display = ["nom", "type", "batiment"]
    list_filter = ["type", "batiment"]


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ["numero", "type", "batiment", "etage", "escalier"]
    list_filter = ["batiment", "type"]
    search_fields = ["numero", "description"]
    inlines = [TantiemeInline, DetentionInline, OccupationInline]


@admin.register(CleRepartition)
class CleRepartitionAdmin(admin.ModelAdmin):
    list_display = ["nom", "base", "total_attribue", "est_complete"]

    @admin.display(description="attribués")
    def total_attribue(self, obj):
        return obj.total_attribue()

    @admin.display(description="complète", boolean=True)
    def est_complete(self, obj):
        return obj.est_complete()


@admin.register(Personne)
class PersonneAdmin(admin.ModelAdmin):
    list_display = ["nom", "prenom", "type", "email", "efface_le"]
    list_filter = ["type", ("efface_le", admin.EmptyFieldListFilter)]
    search_fields = ["nom", "prenom", "email"]

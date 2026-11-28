"""Menu principal : une entrée n'apparaît que si sa vue l'accepterait.

Le droit n'est pas recopié ici : il se lit sur la vue cible (`controle_acces`,
posé par `exige`), puis passe par `peut`, la seule fonction qui décide. Une
entrée vers une vue sans contrôle déclaré lève une erreur plutôt que de
s'afficher.
"""

from django.urls import resolve, reverse

from acces.droits import peut

ENTREES = (
    ("Lots", "lots"),
    ("Incidents", "incidents:liste"),
    ("Documents", "documents:liste"),
    ("Échéances", "echeances:liste"),
    ("Agenda", "agenda:liste"),
    ("Eau", "eau:liste"),
    ("Journal", "audit:journal"),
    ("Copropriété", "identite"),
)


def entrees_visibles(utilisateur):
    menu = []
    for libelle, nom in ENTREES:
        url = reverse(nom)
        action, domaine = resolve(url).func.controle_acces
        if peut(utilisateur, action, domaine):
            menu.append({"libelle": libelle, "url": url})
    return menu


def menu(request):
    """Processeur de contexte : rien pour l'anonyme (aucune requête en base)."""
    if not request.user.is_authenticated:
        return {"menu": []}
    return {"menu": entrees_visibles(request.user)}

from django.urls import path

from acces import views

urlpatterns = [
    path("<str:jeton>/", views.accepter_invitation, name="accepter_invitation"),
]

from allauth.account.adapter import DefaultAccountAdapter

from copro.identite import expediteur, nom_affiche, pied_de_mail


class AdaptateurCompte(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        """Inscription libre fermée : un compte naît d'une invitation."""
        return False

    def get_from_email(self):
        return expediteur()

    def format_email_subject(self, subject):
        """Préfixe « [nom (commune)] » plutôt que le nom d'hôte de la requête."""
        return f"[{nom_affiche()}] {subject}"

    def send_mail(self, template_prefix, email, context):
        """allauth rend ses mails sans requête, donc sans processeur de contexte :
        le pied commun passe ici (gabarit `account/email/base_message.txt`)."""
        context = {"pied_de_mail": pied_de_mail(), **context}
        super().send_mail(template_prefix, email, context)

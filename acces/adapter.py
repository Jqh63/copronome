from allauth.account.adapter import DefaultAccountAdapter


class AdaptateurCompte(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        """Inscription libre fermée : un compte naît d'une invitation."""
        return False

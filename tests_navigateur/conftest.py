import os

import pytest

# Playwright synchrone fait tourner une boucle asyncio dans le fil du test :
# sans ceci, Django refuse l'ORM (SynchronousOnlyOperation).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")


@pytest.fixture(scope="session")
def navigateur():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        yield navigateur
        navigateur.close()


@pytest.fixture
def page(navigateur, live_server):
    contexte = navigateur.new_context(base_url=live_server.url, locale="fr-FR")
    page = contexte.new_page()
    page.set_default_timeout(10_000)
    yield page
    contexte.close()

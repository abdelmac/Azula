"""Lancement Waitress local ou derrière un proxy HTTPS explicitement approuvé."""

import os
from collections.abc import Mapping
from ipaddress import ip_address

from waitress import serve


def server_options(environ: Mapping[str, str]) -> dict:
    try:
        port = int(environ.get("PORT", "8000"))
    except ValueError:
        raise ValueError("PORT doit être un entier entre 1 et 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("PORT doit être un entier entre 1 et 65535.")

    options = {
        "listen": f"0.0.0.0:{port}",
        "threads": 8,
        "clear_untrusted_proxy_headers": True,
    }
    if environ.get("TRUST_HTTPS_PROXY", "0") == "1":
        proxy = environ.get("TRUSTED_PROXY", "").strip()
        if not proxy:
            raise ValueError("TRUST_HTTPS_PROXY=1 exige une valeur explicite pour TRUSTED_PROXY.")
        if proxy != "*":
            try:
                ip_address(proxy)
            except ValueError:
                raise ValueError("TRUSTED_PROXY doit être une adresse IP ; '*' exige un réseau privé maîtrisé.") from None
        # '*' n'est jamais implicite : le déploiement doit isoler l'entrée HTTP
        # du backend et laisser le proxy écraser les en-têtes reçus du client.
        options.update({
            "trusted_proxy": proxy,
            "trusted_proxy_count": 1,
            "trusted_proxy_headers": {"x-forwarded-proto", "x-forwarded-for"},
        })
    return options


def main():
    # L'import charge aussi les variables locales via les paramètres Django.
    from config.wsgi import application

    try:
        options = server_options(os.environ)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    serve(application, **options)


if __name__ == "__main__":
    main()

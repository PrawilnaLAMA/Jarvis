"""Jednorazowe uzyskanie tokenów dostępu USOS (OAuth 1.0a, PIN).

Uruchomienie: py scripts/usos/get_tokens.py  (wymaga: pip install requests-oauthlib)
"""

from common import BASE_URL, require
from requests_oauthlib import OAuth1Session


def get_usos_tokens():
    consumer_key = require("USOS_CONSUMER_KEY")
    consumer_secret = require("USOS_CONSUMER_SECRET")

    print("🔄 KROK 1: Uzyskiwanie Request Token...")
    usos = OAuth1Session(consumer_key, client_secret=consumer_secret)
    # oob = "out of band" – PIN zostanie pokazany na stronie
    extra_data = {"oauth_callback": "oob", "scopes": "studies"}
    try:
        fetch_response = usos.fetch_request_token(BASE_URL + "services/oauth/request_token", data=extra_data)
    except Exception as e:
        print(f"❌ Błąd: {e}")
        return None

    print("\n🔄 KROK 2: Otwórz ten URL w przeglądarce i zaloguj się:")
    print("🔗 " + usos.authorization_url(BASE_URL + "services/oauth/authorize"))
    print("\nPo autoryzacji aplikacji USOS pokaże PIN.")
    oauth_verifier = input("\n🔄 KROK 3: Wprowadź PIN: ")

    print("\n🔄 KROK 4: Uzyskiwanie Access Token...")
    usos = OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=fetch_response.get("oauth_token"),
        resource_owner_secret=fetch_response.get("oauth_token_secret"),
        verifier=oauth_verifier,
    )
    try:
        response = usos.fetch_access_token(BASE_URL + "services/oauth/access_token")
    except Exception as e:
        print(f"❌ Błąd podczas uzyskiwania Access Token: {e}")
        return None

    print("\n🎉 Dopisz do pliku .env:")
    print(f"USOS_ACCESS_TOKEN={response.get('oauth_token')}")
    print(f"USOS_ACCESS_TOKEN_SECRET={response.get('oauth_token_secret')}")
    return response.get("oauth_token"), response.get("oauth_token_secret")


if __name__ == "__main__":
    get_usos_tokens()

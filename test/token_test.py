import requests
from requests_oauthlib import OAuth1Session

# === KONFIGURACJA - WYPEŁNIJ SWOJE DANE ===
CONSUMER_KEY = "HxRNj2XUDcpSjVTr8nVJ"
CONSUMER_SECRET = "cfHysJwHkRmdvT37pbshApDdKA4e3wKubVksTt9Y"
BASE_URL = "https://apps.usos-szkol.pwr.edu.pl/"

def get_usos_tokens():
    # Krok 1: Uzyskanie Request Token
    print("🔄 KROK 1: Uzyskiwanie Request Token...")
    
    usos = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET)
    request_token_url = BASE_URL + "services/oauth/request_token"
    
    # Dodajemy parametr callback (oob = "out of band" - PIN będzie pokazany na stronie)
    extra_data = {
        'oauth_callback': 'oob',
        'scopes': 'studies'  # Zakres dostępu do planu zajęć
    }
    
    try:
        fetch_response = usos.fetch_request_token(request_token_url, data=extra_data)
        print("✅ Request Token uzyskany!")
    except Exception as e:
        print(f"❌ Błąd: {e}")
        return None

    # Krok 2: Generowanie URL do autoryzacji
    print("\n🔄 KROK 2: Autoryzacja w przeglądarce...")
    authorization_url = BASE_URL + "services/oauth/authorize"
    authorization_url = usos.authorization_url(authorization_url)
    
    print("✨ Otwórz ten URL w przeglądarce i zaloguj się:")
    print("🔗 " + authorization_url)
    print("\nPo zalogowaniu i autoryzacji aplikacji, USOS pokaże Ci PIN.")

    # Krok 3: Pobranie PIN od użytkownika
    print("\n🔄 KROK 3: Wprowadź PIN z USOS...")
    oauth_verifier = input("Wprowadź PIN wyświetlony na stronie USOS: ")

    # Krok 4: Wymiana na Access Token
    print("\n🔄 KROK 4: Uzyskiwanie Access Token...")
    access_token_url = BASE_URL + "services/oauth/access_token"
    
    usos = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=fetch_response.get('oauth_token'),
        resource_owner_secret=fetch_response.get('oauth_token_secret'),
        verifier=oauth_verifier
    )
    
    try:
        access_token_response = usos.fetch_access_token(access_token_url)
        access_token = access_token_response.get('oauth_token')
        access_token_secret = access_token_response.get('oauth_token_secret')
        
        print("\n🎉 SUKCES! Oto Twoje tokeny:")
        print(f"ACCESS_TOKEN: {access_token}")
        print(f"ACCESS_TOKEN_SECRET: {access_token_secret}")
        
        return access_token, access_token_secret
        
    except Exception as e:
        print(f"❌ Błąd podczas uzyskiwania Access Token: {e}")
        return None

# Uruchom proces
if __name__ == "__main__":
    tokens = get_usos_tokens()
    if tokens:
        print("\n💾 Zapisz te tokeny w bezpiecznym miejscu!")
        print("🔄 Możesz teraz użyć ich do pobrania planu zajęć.")
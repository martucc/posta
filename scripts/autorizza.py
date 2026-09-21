"""Da lanciare una volta sul PC: crea token.json per il secret GMAIL_TOKEN_JSON.

Serve credentials.json (client OAuth di tipo "App desktop") nella cartella del repo.
Si apre il browser, accedi con 2005niky@gmail.com e accetti. Poi copia tutto il
contenuto di token.json nel secret GMAIL_TOKEN_JSON del repo posta.
Ne credentials.json ne token.json vanno committati: sono nel .gitignore.
"""

from google_auth_oauthlib.flow import InstalledAppFlow

from gmail import SCOPES

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
with open("token.json", "w", encoding="utf-8") as f:
    f.write(creds.to_json())
print("token.json creato: copialo nel secret GMAIL_TOKEN_JSON")

from google_auth_oauthlib.flow import Flow
flow = Flow.from_client_config(
    {"web": {"client_id": "test", "client_secret": "test", "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}},
    scopes=["openid"],
    redirect_uri="http://localhost"
)
url, state = flow.authorization_url()
print("code_verifier:", getattr(flow.oauth2session, "_code_verifier", None))

import os
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

def get_etrade_session():
    load_dotenv("etrade.env")  # Load tokens from .env file

    key = os.getenv("PROD_API_KEY")
    secret = os.getenv("PROD_API_SECRET")
    oauth_token = os.getenv("ACCESS_TOKEN")
    oauth_token_secret = os.getenv("ACCESS_TOKEN_SECRET")

    if not all([key, secret, oauth_token, oauth_token_secret]):
        raise ValueError("Missing one or more required E*TRADE credentials in etrade.env")

    return OAuth1Session(key, secret, oauth_token, oauth_token_secret)
import os
from dotenv import load_dotenv

# Load the env file
load_dotenv("etrade.env")

# Get and print the values
key = os.getenv("ETRADE_API_KEY")
secret = os.getenv("ETRADE_API_SECRET")

print("Key:", key)
print("Secret:", secret)

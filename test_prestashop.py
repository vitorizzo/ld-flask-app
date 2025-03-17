import requests

url = 'https://www.ldenoteca.it/api/products'
api_key = 'GJREIVGGYAMNJVEEUISU3D38S9TGQKBK'

response = requests.get(url, params={'ws_key': api_key})

print(response.status_code)
print(response.text)

import os
import requests
from requests.auth import HTTPBasicAuth
from extensions import db
from models import Immagini, Sincro
from dotenv import load_dotenv
from pathlib import Path
import xmltodict

basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / '.env')

PS_URL = os.getenv("PRESTASHOP_URL")
PS_KEY = os.getenv("PRESTASHOP_KEY")

IMAGES_FOLDER = basedir / 'static' / 'images' / 'products'
IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)


def get_all_products():
    response = requests.get(
        f"{PS_URL}/products",
        params={'ws_key': PS_KEY}
    )
    response.raise_for_status()
    products_data = xmltodict.parse(response.content)
    products = products_data['prestashop']['products']['product']

    for product in products:
        pid = product['@id']
        prod_response = requests.get(
            f"{PS_URL}/products/{pid}",
            params={'ws_key': PS_KEY}
        )
        prod_response.raise_for_status()
        prod_info = xmltodict.parse(prod_response.content)
        prod_data = prod_info['prestashop']['product']

        # Estrazione del nome con gestione della lingua
        lang_name = prod_data['name']['language']
        if isinstance(lang_name, list):
            name = next((item.get('#text', '') for item in lang_name if item.get('@id') == '1'), lang_name[0].get('#text', ''))
        else:
            name = prod_data['name']['language'].get('#text', '')

        # Recupera la descrizione tramite la funzione dedicata
        description = get_product_description(pid)

        # Recupera la reference che serve come cod_art
        cod_art = prod_data.get('reference')
        if not cod_art or not cod_art.strip():
            print(f"⚠️ Prodotto {pid} saltato perché non ha reference.")
            continue  # Salta l'inserimento se non esiste la reference

        product_data = {
            'id': pid,
            'name': name,
            'price': prod_data['price'],
            'cod_art': cod_art,
            'description': description
        }
        yield product_data


def get_product_description(product_id):
    response = requests.get(
        f"{PS_URL}/products/{product_id}",
        params={'ws_key': PS_KEY}
    )
    response.raise_for_status()
    prod_info = xmltodict.parse(response.content)
    prod_data = prod_info['prestashop']['product']

    lang_desc = prod_data.get('description', {}).get('language', '')

    # Se non esiste una descrizione, ritorna una stringa vuota
    if not lang_desc:
        return ""

    if isinstance(lang_desc, list):
        # Usa .get('#text', '') per evitare KeyError se il tag non esiste
        description = next((item.get('#text', '') for item in lang_desc if item.get('@id') == '1'),
                           lang_desc[0].get('#text', ''))
    else:
        description = lang_desc.get('#text', '')

    return description


def get_product_images(product_id, cod_art):
    images_response = requests.get(
        f"{PS_URL}/images/products/{product_id}",
        auth=HTTPBasicAuth(PS_KEY, ''),
        params={'ws_key': PS_KEY}
    )

    images = []

    if images_response.status_code == 200:
        images_info = xmltodict.parse(images_response.content)
        declinations = images_info.get('prestashop', {}).get('image', {}).get('declination', [])
        if not isinstance(declinations, list):
            declinations = [declinations]
        for img in declinations:
            image_id = img['@id']
            image_url = f"{PS_URL}/images/products/{product_id}/{image_id}"
            print(f"Recupero immagine con id: {image_id}")
            image_response = requests.get(
                image_url,
                auth=HTTPBasicAuth(PS_KEY, ''),
                params={'ws_key': PS_KEY}
            )
            if image_response.status_code == 200:
                file_name = f"{product_id}_{image_id}.jpg"
                file_path = IMAGES_FOLDER / file_name

                if file_path.exists():
                    print(f"ℹ️ Immagine {file_name} già presente, salto la copia.")
                else:
                    with open(file_path, 'wb') as f:
                        f.write(image_response.content)
                    print(f"✅ Salvata immagine {file_name} per prodotto {product_id}")

                # Controlla se il record esiste già nel DB
                existing_img = Immagini.query.filter_by(file_img=file_name, cod_art=cod_art).first()
                if existing_img is None:
                    nuova_immagine = Immagini(file_img=file_name, cod_art=cod_art)
                    db.session.add(nuova_immagine)
                    db.session.commit()
                else:
                    print(f"ℹ️ Record DB per {file_name} e {cod_art} già esistente, salto l'inserimento.")

                images.append(file_name)
            else:
                print(f"❌ Errore immagine {image_id} prodotto {product_id}: {image_response.status_code}")
    elif images_response.status_code == 404:
        print(f"⚠️ Prodotto {product_id} non ha immagini (404).")
    else:
        print(f"❌ Errore recupero immagini prodotto {product_id}: {images_response.status_code}")

    return images

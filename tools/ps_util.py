import os
from pprint import pprint

import requests
from requests.auth import HTTPBasicAuth
from extensions import db
from models import Immagini, Sincro, SchedeProdotti
from dotenv import load_dotenv
from pathlib import Path
import xmltodict
import xml.etree.ElementTree as ET

basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / '.env')

PS_URL = os.getenv("PRESTASHOP_URL")
PS_KEY = os.getenv("PRESTASHOP_KEY")

IMAGES_FOLDER = basedir / 'static' / 'images' / 'products'
IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)


def get_product_by_code(cod_art):
    response = requests.get(
        f"{PS_URL}/products/?ws_key={PS_KEY}&filter[reference]={cod_art}"
    )
    # print(f"Status Code: {response.status_code}")  # Mostra il codice di stato
    # print(f"Response Text: {response.text}")  # Mostra il contenuto della risposta

    if response.status_code == 200:
        try:
            root = ET.fromstring(response.text)
            product = root.find(".//product")
            if product is not None and "id" in product.attrib:
                p_info = get_product_details(product.attrib["id"])
                # pprint(p_info)
                # print(p_info['description'])
                #print(get_product_descriptions(product.attrib["id"]))
                return p_info['description']
        except ET.ParseError:
            print("Errore: Impossibile analizzare l'XML")

    return None


def get_product_details(product_id):
    """ Ottiene i dettagli completi del prodotto """
    url = f"{PS_URL}/products/{product_id}?ws_key={PS_KEY}"

    response = requests.get(url)

    if response.status_code == 200:
        try:
            root = ET.fromstring(response.text)

            # Estrarre i dettagli del prodotto
            name = root.find(".//name/language")
            description = root.find(".//description/language")
            price = root.find(".//price")
            reference = root.find(".//reference")

            product_info = {
                "id": product_id,
                "reference": reference.text if reference is not None else None,
                "name": name.text if name is not None else None,
                "description": description.text if description is not None else None,
                "price": price.text if price is not None else None,
            }

            return product_info

        except ET.ParseError:
            print("Errore: Impossibile analizzare l'XML")

    return None


def get_all_products():
    db.create_all()
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
        description = get_product_descriptions(pid)

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


def get_product_descriptions(product_id):
    response = requests.get(
        f"{PS_URL}/products/{product_id}",
        params={'ws_key': PS_KEY}
    )
    response.raise_for_status()
    prod_info = xmltodict.parse(response.content)
    prod_data = prod_info['prestashop']['product']
    # print(f"prod_data contiene: {prod_data}")
    cod_art = prod_data.get('reference')
    lang_desc = prod_data.get('description', {}).get('language', '')
    lang_short_desc = prod_data.get('description_short', {}).get('language', '')
    # Se non esiste una descrizione, ritorna una stringa vuota
    if not lang_desc and cod_art:
        return ""
    descriptions = []
    if isinstance(lang_desc, list):
        # Usa .get('#text', '') per evitare KeyError se il tag non esiste
        description = next((item.get('#text', '') for item in lang_desc if item.get('@id') == '1'),
                           lang_desc[0].get('#text', ''))
    else:
        description = lang_desc.get('#text', '')
    descriptions.append(description)
    if isinstance(lang_short_desc, list):
        # Usa .get('#text', '') per evitare KeyError se il tag non esiste
        description_short = next((item.get('#text', '') for item in lang_short_desc if item.get('@id') == '1'),
                           lang_short_desc[0].get('#text', ''))
    else:
        description_short = lang_short_desc.get('#text', '')
    descriptions.append(description_short)
    # Controlla se il record esiste già nel DB
    existing_sched = SchedeProdotti.query.filter_by(cod_art=cod_art).first()
    if existing_sched is None:
        nuova_scheda = SchedeProdotti(descrizione=description, short=description_short, cod_art=cod_art)
        db.session.add(nuova_scheda)
        db.session.commit()
    else:
        print(f"ℹ️ Record DB per {cod_art} già esistente, salto l'inserimento.")
    return descriptions


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

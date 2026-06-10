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
from tools.log_utils import get_logger

logger = get_logger('ps_util')

basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / '.env', override=False)
load_dotenv(basedir / '.env.local', override=True)
load_dotenv(basedir / '.env.defaults', override=False)

PS_URL = os.getenv("PRESTASHOP_URL")
PS_KEY = os.getenv("PRESTASHOP_KEY")

IMAGES_FOLDER = basedir / 'static' / 'images' / 'products'
IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)

def get_product_by_code(cod_art):
    logger.info(f"get_product_by_code(): Cerco il prodotto con codice {cod_art}")
    try:
        response = requests.get(f"{PS_URL}/products/?ws_key={PS_KEY}&filter[reference]={cod_art}")
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            product = root.find(".//product")
            if product is not None and "id" in product.attrib:
                p_info = get_product_details(product.attrib["id"])
                return p_info['description']
    except ET.ParseError:
        logger.exception("Errore durante il parsing XML nella get_product_by_code")
    except Exception as e:
        logger.exception("Errore generico nella get_product_by_code")
    return None

def get_product_details(product_id):
    url = f"{PS_URL}/products/{product_id}?ws_key={PS_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            name = root.find(".//name/language")
            description = root.find(".//description/language")
            price = root.find(".//price")
            reference = root.find(".//reference")

            return {
                "id": product_id,
                "reference": reference.text if reference is not None else None,
                "name": name.text if name is not None else None,
                "description": description.text if description is not None else None,
                "price": price.text if price is not None else None,
            }
    except ET.ParseError:
        logger.exception("Errore durante il parsing XML nella get_product_details")
    except Exception as e:
        logger.exception("Errore generico nella get_product_details")
    return None


def get_all_products():
    logger.info("get_all_products(): Inizio recupero lista prodotti da Prestashop")
    db.create_all()
    response = requests.get(f"{PS_URL}/products", params={'ws_key': PS_KEY})
    response.raise_for_status()
    products_data = xmltodict.parse(response.content)
    products = products_data['prestashop']['products']['product']
    if not isinstance(products, list):
        products = [products]

    for product in products:
        pid = product['@id']
        prod_response = requests.get(f"{PS_URL}/products/{pid}", params={'ws_key': PS_KEY})
        prod_response.raise_for_status()
        prod_info = xmltodict.parse(prod_response.content)
        prod_data = prod_info['prestashop']['product']

        lang_name = prod_data['name']['language']
        name = next((item.get('#text', '') for item in lang_name if item.get('@id') == '1'), lang_name[0].get('#text', '')) if isinstance(lang_name, list) else lang_name.get('#text', '')

        cod_art = prod_data.get('reference')
        if not cod_art or not cod_art.strip():
            logger.warning(f"Prodotto {pid} senza reference, salto.")
            continue
        cod_art = cod_art.strip()

        description = get_product_descriptions(pid)

        yield {
            'id': pid,
            'name': name,
            'price': prod_data['price'],
            'cod_art': cod_art,
            'description': description
        }

def get_product_descriptions(product_id):
    logger.info(f"get_product_descriptions(): Recupero descrizione per prodotto {product_id}")
    response = requests.get(f"{PS_URL}/products/{product_id}", params={'ws_key': PS_KEY})
    response.raise_for_status()
    prod_info = xmltodict.parse(response.content)
    prod_data = prod_info['prestashop']['product']
    cod_art = prod_data.get('reference')
    if not cod_art or not cod_art.strip():
        logger.warning(f"Prodotto {product_id} senza reference, salto salvataggio scheda.")
        return ["", ""]
    cod_art = cod_art.strip()

    lang_desc = prod_data.get('description', {}).get('language', '')
    lang_short_desc = prod_data.get('description_short', {}).get('language', '')

    if not lang_desc and cod_art:
        return ["", ""]

    description = next((item.get('#text', '') for item in lang_desc if item.get('@id') == '1'), lang_desc[0].get('#text', '')) if isinstance(lang_desc, list) else lang_desc.get('#text', '')
    description_short = next((item.get('#text', '') for item in lang_short_desc if item.get('@id') == '1'), lang_short_desc[0].get('#text', '')) if isinstance(lang_short_desc, list) else lang_short_desc.get('#text', '')

    if not SchedeProdotti.query.filter_by(cod_art=cod_art).first():
        db.session.add(SchedeProdotti(descrizione=description, short=description_short, cod_art=cod_art))
        logger.info(f"Salvata nuova scheda prodotto per {cod_art}")
    else:
        logger.info(f"Record per {cod_art} già esistente, nessun inserimento")

    return [description, description_short]

def get_product_images(product_id, cod_art):
    logger.info(f"get_product_images(): Recupero immagini per prodotto {product_id}")
    images = []

    images_response = requests.get(f"{PS_URL}/images/products/{product_id}", auth=HTTPBasicAuth(PS_KEY, ''), params={'ws_key': PS_KEY})
    if images_response.status_code == 200:
        images_info = xmltodict.parse(images_response.content)
        declinations = images_info.get('prestashop', {}).get('image', {}).get('declination', [])
        if not isinstance(declinations, list):
            declinations = [declinations]
        for img in declinations:
            image_id = img['@id']
            image_url = f"{PS_URL}/images/products/{product_id}/{image_id}"
            image_response = requests.get(image_url, auth=HTTPBasicAuth(PS_KEY, ''), params={'ws_key': PS_KEY})
            if image_response.status_code == 200:
                file_name = f"{product_id}_{image_id}.jpg"
                file_path = IMAGES_FOLDER / file_name
                if not file_path.exists():
                    with open(file_path, 'wb') as f:
                        f.write(image_response.content)
                    logger.info(f"Salvata immagine: {file_name}")
                else:
                    logger.debug(f"Immagine già presente: {file_name}")

                if not Immagini.query.filter_by(file_img=file_name, cod_art=cod_art).first():
                    db.session.add(Immagini(file_img=file_name, cod_art=cod_art))
                    db.session.commit()
                else:
                    logger.debug(f"Record Immagini già presente per {file_name} - {cod_art}")
                images.append(file_name)
            else:
                logger.warning(f"Errore nel recupero immagine {image_id}: HTTP {image_response.status_code}")
    elif images_response.status_code == 404:
        logger.warning(f"Prodotto {product_id} non ha immagini (404)")
    else:
        logger.error(f"Errore recupero immagini prodotto {product_id}: {images_response.status_code}")

    return images

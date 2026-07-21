from __future__ import annotations

import json
from datetime import datetime, timezone
from time import sleep
from urllib.parse import urlparse

import requests
from flask import current_app

from extensions import db
from models import SocialEventPost


class MetaPublishError(RuntimeError):
    pass


def _graph_url(path: str) -> str:
    version = str(current_app.config.get("META_GRAPH_API_VERSION") or "v20.0").strip().strip("/")
    if not version.startswith("v"):
        version = f"v{version}"
    return f"https://graph.facebook.com/{version}/{path.lstrip('/')}"


def _request(method: str, path: str, *, data=None, params=None):
    try:
        response = requests.request(method, _graph_url(path), data=data, params=params, timeout=(10, 45))
        body = response.json()
    except requests.RequestException as exc:
        raise MetaPublishError(f"Connessione a Meta non riuscita: {exc}") from exc
    except ValueError as exc:
        raise MetaPublishError("Meta ha restituito una risposta non valida.") from exc
    if not response.ok or body.get("error"):
        error = body.get("error") or {}
        message = error.get("message") or f"Errore HTTP {response.status_code}"
        code = error.get("code")
        raise MetaPublishError(f"{message}{f' (codice {code})' if code else ''}")
    return body


def _image_urls(post: SocialEventPost) -> list[str]:
    media = ((post.payload or {}).get("media") or {})
    items = media.get("carousel_items") or media.get("week_items") or []
    urls = []
    for item in items:
        url = (item.get("image_url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.netloc and url not in urls:
            urls.append(url)
    return urls[:10]


def _facebook_caption(post: SocialEventPost) -> str:
    return f"{post.caption.rstrip()}\n\n{post.public_url}"


def publish_facebook(post: SocialEventPost) -> dict:
    page_id = str(current_app.config.get("META_PAGE_ID") or "").strip()
    token = str(current_app.config.get("META_PAGE_ACCESS_TOKEN") or "").strip()
    if not page_id or not token:
        raise MetaPublishError("Configurazione Facebook incompleta: Page ID o Page access token mancante.")

    image_urls = _image_urls(post)
    if image_urls:
        attached = []
        for image_url in image_urls:
            photo = _request("POST", f"{page_id}/photos", data={
                "url": image_url,
                "published": "false",
                "access_token": token,
            })
            attached.append({"media_fbid": photo["id"]})
        data = {"message": _facebook_caption(post), "access_token": token}
        for index, media in enumerate(attached):
            data[f"attached_media[{index}]"] = json.dumps(media)
        result = _request("POST", f"{page_id}/feed", data=data)
    else:
        result = _request("POST", f"{page_id}/feed", data={
            "message": post.caption,
            "link": post.public_url,
            "access_token": token,
        })
    external_id = result.get("id")
    return {
        "status": "published",
        "external_id": external_id,
        "permalink": f"https://www.facebook.com/{external_id.replace('_', '/posts/')}" if external_id and "_" in external_id else None,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def _instagram_caption(post: SocialEventPost) -> str:
    hashtags = str(current_app.config.get("META_INSTAGRAM_DEFAULT_HASHTAGS") or "").strip()
    pieces = [post.caption.rstrip(), post.public_url]
    if hashtags:
        pieces.append(hashtags)
    return "\n\n".join(pieces)


def _wait_for_container(container_id: str, token: str):
    for _ in range(12):
        result = _request("GET", container_id, params={"fields": "status_code,status", "access_token": token})
        status = result.get("status_code")
        if status == "FINISHED":
            return
        if status in {"ERROR", "EXPIRED"}:
            raise MetaPublishError(result.get("status") or f"Preparazione contenuto Instagram: {status}.")
        sleep(1)
    raise MetaPublishError("Instagram sta ancora preparando le immagini; riprovare tra poco.")


def publish_instagram(post: SocialEventPost) -> dict:
    account_id = str(current_app.config.get("META_INSTAGRAM_ACCOUNT_ID") or "").strip()
    token = str(current_app.config.get("META_PAGE_ACCESS_TOKEN") or "").strip()
    if not account_id or not token:
        raise MetaPublishError("Configurazione Instagram incompleta: Account ID o Page access token mancante.")
    image_urls = _image_urls(post)
    if not image_urls:
        raise MetaPublishError("Instagram richiede almeno una locandina pubblica HTTPS.")

    caption = _instagram_caption(post)
    if len(image_urls) == 1:
        container = _request("POST", f"{account_id}/media", data={
            "image_url": image_urls[0], "caption": caption, "access_token": token,
        })
    else:
        children = []
        for image_url in image_urls:
            child = _request("POST", f"{account_id}/media", data={
                "image_url": image_url, "is_carousel_item": "true", "access_token": token,
            })
            _wait_for_container(child["id"], token)
            children.append(child["id"])
        container = _request("POST", f"{account_id}/media", data={
            "media_type": "CAROUSEL", "children": ",".join(children),
            "caption": caption, "access_token": token,
        })
    _wait_for_container(container["id"], token)
    result = _request("POST", f"{account_id}/media_publish", data={
        "creation_id": container["id"], "access_token": token,
    })
    external_id = result.get("id")
    permalink = None
    if external_id:
        permalink = _request("GET", external_id, params={"fields": "permalink", "access_token": token}).get("permalink")
    return {
        "status": "published", "external_id": external_id, "permalink": permalink,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def publish_social_event_post(post: SocialEventPost, destinations) -> dict:
    requested = [name for name in ("facebook", "instagram") if name in set(destinations or [])]
    payload = dict(post.payload or {})
    results = dict(payload.get("publication_results") or {})
    for destination in requested:
        if (results.get(destination) or {}).get("status") == "published":
            continue
        try:
            results[destination] = (publish_facebook(post) if destination == "facebook" else publish_instagram(post))
        except MetaPublishError as exc:
            results[destination] = {
                "status": "failed", "error": str(exc),
                "attempted_at": datetime.now(timezone.utc).isoformat(),
            }

    payload["publication_results"] = results
    post.payload = payload
    post.destinations = sorted(set((post.destinations or []) + requested))
    successful = [name for name in requested if (results.get(name) or {}).get("status") == "published"]
    failed = [name for name in requested if (results.get(name) or {}).get("status") == "failed"]
    if successful and not failed:
        post.status = "published"
        post.published_at = post.published_at or datetime.now(timezone.utc)
        post.status_message = "Pubblicato su " + " e ".join(successful) + "."
    elif successful:
        post.status = "partial"
        post.status_message = "Pubblicato su " + ", ".join(successful) + "; non riuscito su " + ", ".join(failed) + "."
    else:
        post.status = "failed"
        post.status_message = "Pubblicazione non riuscita su " + ", ".join(failed or requested) + "."
    db.session.commit()
    return results

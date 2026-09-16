"""Helper condivisi per gli import di catalogo da API esterne
(Scryfall per Magic, Pokémon TCG API, YGOProDeck per Yu-Gi-Oh!...)."""

import json
import time
import unicodedata
import urllib.error
import urllib.request

from django.core.files.base import ContentFile

from cards.models import Card, Expansion, Game

# User-Agent "umano": senza, alcune API (es. Cloudflare di Scryfall)
# rispondono 400 alle richieste programmatiche.
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/125.0 Safari/537.36')
REQUEST_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': 'application/json, text/plain, */*',
}


def fetch_json(url, timeout=30, extra_headers=None, retries=3):
    """GET JSON con User-Agent configurato e retry sui 5xx (API instabili)."""
    headers = dict(REQUEST_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == retries:
                raise
        except urllib.error.URLError:
            if attempt == retries:
                raise
        time.sleep(attempt * 1.5)  # backoff progressivo
    raise RuntimeError(f'Impossibile scaricare {url}')


def _fold(value):
    """Normalizza il nome senza accenti e in minuscolo (Pokémon == Pokemon)."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', value)
        if not unicodedata.combining(c)
    ).lower()


def resolve_game(game_name):
    """Riusa un gioco già presente se il nome coincide (anche senza accenti)
    oppure "inizia" con la parte principale (es. 'Magic' vs 'Magic: The Gathering')."""
    folded = _fold(game_name)
    alias = game_name.split(':')[0].strip()

    for game in Game.objects.all():
        fname = _fold(game.name)
        if fname == folded:
            return game

    if alias:
        falias = _fold(alias)
        for game in Game.objects.all():
            fname = _fold(game.name)
            if falias in fname or fname in falias:
                return game

    return Game.objects.create(name=game_name)


def get_or_create_expansion(game, code, name, release_date=None):
    """Espansione idempotente per codice."""
    expansion, _ = Expansion.objects.get_or_create(
        code=code.upper(),
        defaults={
            'name': name,
            'game': game,
            'release_date': release_date or None,
        },
    )
    return expansion


def upsert_card(expansion, name, number, rarity, image_url=''):
    """Crea la carta oppure completa i campi vuoti (re-run idempotente).

    Ritorna (card_obj, created).
    """
    card_obj, created = Card.objects.get_or_create(
        expansion=expansion,
        number=number,
        defaults={'name': name, 'rarity': rarity, 'image_url': image_url},
    )
    if not created:
        updates = {}
        if not card_obj.name and name:
            updates['name'] = name
        if not card_obj.rarity and rarity:
            updates['rarity'] = rarity
        if not card_obj.image_url and image_url:
            updates['image_url'] = image_url
        if updates:
            for key, value in updates.items():
                setattr(card_obj, key, value)
            card_obj.save(update_fields=list(updates.keys()))
    return card_obj, created


def download_image(card_obj, image_url):
    """Scarica la copia locale dell'immagine remota sul campo Image.

    Ritorna True se scaricata; il salvataggio del record va fatto da chi chiama.
    """
    try:
        req = urllib.request.Request(image_url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, ValueError):
        return False
    ext = 'png' if '.png' in image_url else 'jpg'
    filename = f"{card_obj.number.replace('/', '_')}.{ext}"
    card_obj.image.save(filename, ContentFile(data), save=False)
    return True

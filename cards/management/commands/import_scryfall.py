"""Management command: importa il catalogo Magic: The Gathering da Scryfall.

L'importazione è idempotente: rieseguirlo non duplica nulla e anzi completa
le carte già presenti (metti image_url/rarity mancanti).

Esempi:
  python manage.py import_scryfall --sets one,neo,woe
  python manage.py import_scryfall --sets one --limit 50 --download-images
"""

import time
from urllib.parse import urlencode

from django.core.management.base import BaseCommand

from cards.importers import download_image, fetch_json, resolve_game, upsert_card
from cards.models import Expansion

DEFAULT_SETS = ['one', 'neo', 'woe', 'mom', 'bro']
SCRYFALL_API = 'https://api.scryfall.com'
SETS_URL = f'{SCRYFALL_API}/sets'


def pick_image_url(card_data, prefer='png'):
    """Le immagini possono stare sulla carta oppure su card_faces (carte bifacciali)."""
    imgs = card_data.get('image_uris')
    if not imgs and card_data.get('card_faces'):
        imgs = card_data['card_faces'][0].get('image_uris')
    if not imgs:
        return ''
    for key in (prefer, 'normal', 'small', 'large'):
        if imgs.get(key):
            return imgs[key]
    return ''


class Command(BaseCommand):
    help = 'Importa il catalogo Magic da Scryfall: giochi, espansioni e carte con immagini.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sets', default=','.join(DEFAULT_SETS),
            help='Codici Scryfall separati da virgola (es. one,neo,woe).'
        )
        parser.add_argument('--game-name', default='Magic: The Gathering')
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Numero massimo totale di carte NUOVE importate (0 = senza limite).'
        )
        parser.add_argument(
            '--max-per-set', type=int, default=0,
            help='Numero massimo di carte importate per espansione (0 = tutte).'
        )
        parser.add_argument(
            '--download-images', action='store_true',
            help='Scarica copie locali (jpg normale) in media/cards/catalog/.'
        )
        parser.add_argument(
            '--full-images', action='store_true',
            help='Con --download-images usa i PNG ad alta risoluzione invece dei jpg.'
        )
        parser.add_argument(
            '--sleep', type=float, default=0.15,
            help="Pausa tra le richieste in secondi (il rate limit di Scryfall è ~10 req/s)."
        )

    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        set_codes = [c.strip().lower() for c in options['sets'].split(',') if c.strip()]
        if not set_codes:
            self.stderr.write('Nessun set valido fornito (--sets).')
            return

        game = resolve_game(options['game_name'])

        # Un solo fetch per prendere i metadati di tutte le espansioni richieste
        sets_payload = fetch_json(SETS_URL)
        sets_by_code = {s['code'].lower(): s for s in sets_payload.get('data', [])}

        total_created = 0
        for code in set_codes:
            created = self.import_set(game, code, options, sets_by_code)
            total_created += created
            if options['limit'] and total_created >= options['limit']:
                self.stdout.write(self.style.WARNING(
                    f'Limite globale raggiunto ({options["limit"]}). Fermo.'
                ))
                break

        self.stdout.write(self.style.SUCCESS(
            f'Fine: {total_created} nuove carte importate.'
        ))

    # ------------------------------------------------------------------

    def import_set(self, game, code, options, sets_by_code):
        set_meta = sets_by_code.get(code)
        if not set_meta:
            self.stdout.write(self.style.WARNING(f'Nessun set "{code}" su Scryfall, salto.'))
            return 0

        released = set_meta.get('released_at')
        expansion, _ = Expansion.objects.get_or_create(
            code=code.upper(),
            defaults={
                'name': set_meta['name'],
                'game': game,
                'release_date': released or None,
            },
        )
        self.stdout.write(f'Importazione "{set_meta["name"]}" ({code})...')

        created_count = 0
        processed = 0
        max_per_set = options['max_per_set']
        url = self.cards_search_url(code)

        while url:
            payload = fetch_json(url)
            for card_data in payload.get('data', []):
                if max_per_set and processed >= max_per_set:
                    break
                processed += 1

                ref_url = pick_image_url(card_data, prefer='png')
                created = self.create_or_update_card(
                    expansion, card_data, ref_url, options
                )
                if created:
                    created_count += 1

            url = payload.get('next_page') if payload.get('has_more') else None
            time.sleep(options['sleep'])

        self.stdout.write(self.style.SUCCESS(
            f'  {code}: {created_count} create, {processed} esaminate.'
        ))
        return created_count

    def cards_search_url(self, code):
        query = urlencode({
            'q': f'set:{code}',
            'unique': 'prints',
            'order': 'set',
        })
        return f'{SCRYFALL_API}/cards/search?{query}'

    def create_or_update_card(self, expansion, card_data, ref_url, options):
        name = card_data.get('name', '')
        number = str(card_data.get('collector_number', ''))
        rarity = card_data.get('rarity', '')

        card_obj, created = upsert_card(
            expansion, name, number, rarity, image_url=ref_url,
        )

        if options['download_images'] and card_obj.image_url and not card_obj.image:
            prefer = 'png' if options['full_images'] else 'normal'
            dl_url = pick_image_url(card_data, prefer=prefer)
            if dl_url and download_image(card_obj, dl_url):
                card_obj.save(update_fields=['image'])

        return created


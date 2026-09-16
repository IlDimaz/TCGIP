"""Management command: importa il catalogo Pokémon TCG dalla Pokémon TCG API.

API ufficiale (https://docs.pokemontcg.io): gratuita, PNG delle carte via
images.large. Senza chiave funziona con rate limit più basso; con --api-key
(sotto "X-Api-Key") i limiti salgono.

Esempi:
  python manage.py import_pokemon --sets sv1,sv2
  python manage.py import_pokemon --sets base1 --api-key TUO_KEY --download-images
"""

import time
from datetime import datetime

from django.core.management.base import BaseCommand

from cards.importers import (
    download_image,
    fetch_json,
    get_or_create_expansion,
    resolve_game,
    upsert_card,
)

POKEMON_API = 'https://api.pokemontcg.io/v2'
CARDS_URL = f'{POKEMON_API}/cards'
PAGE_SIZE = 250
DEFAULT_SETS = ['sv1']


class Command(BaseCommand):
    help = 'Importa il catalogo Pokémon TCG: set + carte con immagini (PNG).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sets', default=','.join(DEFAULT_SETS),
            help='ID dei set separati da virgola (es. sv1,sv2,base1,mew).'
        )
        parser.add_argument('--game-name', default='Pokémon')
        parser.add_argument(
            '--api-key', default='',
            help='Chiave della Pokémon TCG API per rate limit più alti (opzionale).'
        )
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Numero massimo totale di carte NUOVE importate (0 = senza limite).'
        )
        parser.add_argument(
            '--download-images', action='store_true',
            help='Scarica copie locali (PNG) in media/cards/catalog/.'
        )
        parser.add_argument(
            '--sleep', type=float, default=0.2,
            help='Pausa tra le richieste in secondi.'
        )

    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        set_ids = [s.strip().lower() for s in options['sets'].split(',') if s.strip()]
        if not set_ids:
            self.stderr.write('Nessun set valido fornito (--sets).')
            return

        self.extra_headers = (
            {'X-Api-Key': options['api_key']} if options['api_key'] else None
        )
        game = resolve_game(options['game_name'])

        total_created = 0
        for set_id in set_ids:
            created = self.import_set(game, set_id, options)
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
    def import_set(self, game, set_id, options):
        self.stdout.write(f'Importazione set "{set_id}"...')

        expansion = None  # creato dal primo card_data['set'] incontrato
        created_count = 0
        processed = 0
        max_per_set = options['limit']
        page = 1

        while True:
            payload = fetch_json(
                f'{CARDS_URL}?q=set.id:{set_id}&pageSize={PAGE_SIZE}&page={page}',
                extra_headers=self.extra_headers,
            )
            data = payload.get('data', [])
            if not data and expansion is None:
                self.stdout.write(self.style.WARNING(f'Nessuna carta per "{set_id}", salto.'))
                return 0

            for card_data in data:
                if max_per_set and processed >= max_per_set:
                    break
                processed += 1

                if expansion is None:
                    set_obj = card_data.get('set', {})
                    released = self.parse_release(set_obj.get('releaseDate'))
                    expansion = get_or_create_expansion(
                        game, set_obj.get('id', set_id), set_obj.get('name', set_id), released,
                    )
                    self.stdout.write(f'  -> "{expansion.name}" ({expansion.code})')

                images = card_data.get('images', {})
                image_url = images.get('large') or images.get('small') or ''
                created = self.import_card(
                    expansion, card_data, image_url, options['download_images'],
                )
                if created:
                    created_count += 1

            if max_per_set and processed >= max_per_set:
                break
            page += 1
            total_count = payload.get('totalCount', 0)
            if not data or len(data) < PAGE_SIZE or (page * PAGE_SIZE) >= total_count:
                break
            time.sleep(options['sleep'])

        self.stdout.write(self.style.SUCCESS(
            f'  {set_id}: {created_count} create, {processed} esaminate.'
        ))
        return created_count

    @staticmethod
    def parse_release(raw):
        if not raw:
            return None
        try:
            return datetime.strptime(raw, '%Y/%m/%d').date()
        except ValueError:
            return None

    def import_card(self, expansion, card_data, image_url, download):
        name = card_data.get('name', '')
        number = str(card_data.get('number', ''))
        rarity = card_data.get('rarity', '') or ''
        card_obj, created = upsert_card(
            expansion, name, number, rarity, image_url=image_url,
        )
        if download and card_obj.image_url and not card_obj.image:
            if download_image(card_obj, card_obj.image_url):
                card_obj.save(update_fields=['image'])
        return created

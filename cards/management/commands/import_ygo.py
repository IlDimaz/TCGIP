"""Management command: importa il catalogo Yu-Gi-Oh! da YGOProDeck.

API pubblica senza chiave (https://db.ygoprodeck.com). Le immagini sono jpg
(card_images). Il numero di carta è estratto dal set_code (es. JUSH-EN040 -> 040).

Esempi:
  python manage.py import_ygo --sets "Justice Hunters"
  python manage.py import_ygo --sets "Legend of Blue Eyes White Dragon" --download-images
"""

import re
from urllib.parse import quote

from django.core.management.base import BaseCommand

from cards.importers import (
    download_image,
    fetch_json,
    get_or_create_expansion,
    resolve_game,
    upsert_card,
)

YGO_API = 'https://db.ygoprodeck.com/api/v7'
CARDINFO_URL = f'{YGO_API}/cardinfo.php'


class Command(BaseCommand):
    help = 'Importa il catalogo Yu-Gi-Oh!: set + carte con immagini (JPG).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sets', required=True,
            help='Nomi dei set separati da virgola (es. "Justice Hunters,Legend of Blue Eyes White Dragon").'
        )
        parser.add_argument('--game-name', default='Yu-Gi-Oh!')
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Numero massimo totale di carte NUOVE importate (0 = senza limite).'
        )
        parser.add_argument(
            '--download-images', action='store_true',
            help='Scarica copie locali (JPG) in media/cards/catalog/.'
        )

    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        set_names = [s.strip() for s in options['sets'].split(',') if s.strip()]
        if not set_names:
            self.stderr.write('Specifica almeno un set con --sets.')
            return

        game = resolve_game(options['game_name'])

        total_created = 0
        for set_name in set_names:
            created = self.import_set(game, set_name)
            total_created += created
            if options['limit'] and total_created >= options['limit']:
                self.stdout.write(self.style.WARNING(
                    f'Limite raggiunto ({options["limit"]}). Fermo.'
                ))
                break

        self.stdout.write(self.style.SUCCESS(
            f'Fine: {total_created} nuove carte importate.'
        ))

    # ------------------------------------------------------------------
    def import_set(self, game, set_name):
        payload = fetch_json(f'{CARDINFO_URL}?cardset={quote(set_name)}')
        data = payload.get('data', [])
        if not data:
            self.stdout.write(self.style.WARNING(f'Nessun risultato per "{set_name}", salto.'))
            return 0

        code = self.set_code_for(data, set_name)
        expansion = get_or_create_expansion(game, code, set_name)
        self.stdout.write(f'Importazione "{set_name}" ({code})...')

        created_count = 0
        for card_data in data:
            entry = next(
                (s for s in card_data.get('card_sets', []) if s.get('set_name') == set_name),
                None,
            )
            set_code = (entry or {}).get('set_code', '')
            number = self.extract_number(set_code)
            rarity = (
                (entry or {}).get('set_rarity_code', '')
                or (entry or {}).get('set_rarity', '')
                or ''
            )
            images = card_data.get('card_images') or []
            image_url = images[0].get('image_url', '') if images else ''

            card_obj, created = upsert_card(
                expansion,
                card_data.get('name', ''),
                number,
                rarity,
                image_url=image_url,
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'  {set_name}: {created_count} create, {len(data)} esaminate.'
        ))
        return created_count

    @staticmethod
    def set_code_for(data, set_name):
        """Codice espansione dal primo set_code trovato (es. JUSH-EN040 -> JUSH)."""
        for card in data:
            for entry in card.get('card_sets', []):
                set_code = entry.get('set_code', '')
                if entry.get('set_name') == set_name and set_code:
                    m = re.match(r'^([A-Z0-9]{1,8})-', set_code)
                    if m:
                        return m.group(1).upper()
        # fallback: acronimo dal nome del set
        initials = ''.join(w[0] for w in set_name.split() if w[0].isalnum())[:6].upper()
        return initials or 'YGO'

    @staticmethod
    def extract_number(set_code):
        """Numero di carta: ultimo numero nel set_code (JUSH-EN040 -> 040)."""
        m = re.search(r'(\d+)$', set_code)
        return m.group(1) if m else ''

from django.test import TestCase
from django.urls import reverse
from users.models import User
from cards.models import Game, Expansion, Card, OwnedCard, ValueSnapshot


class CollectionViewsTestCase(TestCase):
    def setUp(self):
        # Due utenti distinti, per verificare che uno non veda/tocchi le carte dell'altro
        self.user1 = User.objects.create_user(username='user1', password='testpass123')
        self.user2 = User.objects.create_user(username='user2', password='testpass123')

        # Catalogo minimo necessario per creare una OwnedCard
        game = Game.objects.create(name='Pokémon TCG')
        expansion = Expansion.objects.create(name='Base', code='BASE', game=game)
        self.card = Card.objects.create(name='Charizard', expansion=expansion, number='4', rarity='Rare')

        # Una OwnedCard che appartiene a user1
        self.owned_card = OwnedCard.objects.create(
            card=self.card, owner=self.user1, status='owned'
        )

    def test_collection_requires_login(self):
        # Senza login, ci si aspetta un redirect (302) verso la pagina di login
        response = self.client.get(reverse('collection'))
        self.assertEqual(response.status_code, 302)

    def test_collection_accessible_when_logged_in(self):
        # Con login, la pagina deve caricarsi correttamente (200)
        self.client.login(username='user1', password='testpass123')
        response = self.client.get(reverse('collection'))
        self.assertEqual(response.status_code, 200)

    def test_user_cannot_edit_others_card(self):
        # user2 prova a modificare una carta che appartiene a user1
        self.client.login(username='user2', password='testpass123')
        response = self.client.get(reverse('collection-edit', args=[self.owned_card.pk]))
        # get_queryset() filtra per owner, quindi la carta "non esiste" per user2 -> 404
        self.assertEqual(response.status_code, 404)

    def test_user_can_edit_own_card(self):
        # user1 invece deve poterci accedere senza problemi
        self.client.login(username='user1', password='testpass123')
        response = self.client.get(reverse('collection-edit', args=[self.owned_card.pk]))
        self.assertEqual(response.status_code, 200)
        
class StaffOnlyImportTestCase(TestCase):
    def setUp(self):
        self.regular_user = User.objects.create_user(username='regular', password='testpass123')
        self.staff_user = User.objects.create_user(
            username='staffmember', password='testpass123', is_staff=True
        )

    def test_regular_user_cannot_access_import(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('import-cards'))
        # staff_member_required reindirizza chi non è staff
        self.assertNotEqual(response.status_code, 200)

    def test_staff_user_can_access_import(self):
        self.client.login(username='staffmember', password='testpass123')
        response = self.client.get(reverse('import-cards'))
        self.assertEqual(response.status_code, 200)

    def test_import_cards_with_new_expansion_and_code(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username='staffmember', password='testpass123')
        game = Game.objects.create(name='One Piece')
        csv_content = b"Name,Number,Rarity\nMonkey D. Luffy,OP03-001,L\nRoronoa Zoro,OP03-002,SR\n"
        csv_file = SimpleUploadedFile("cards.csv", csv_content, content_type="text/csv")

        response = self.client.post(reverse('import-cards'), {
            'game': game.id,
            'expansion': '',
            'new_expansion_name': 'Pillars of Strength',
            'new_expansion_code': 'OP-03',
            'csv_file': csv_file,
        })
        self.assertEqual(response.status_code, 302)
        expansion = Expansion.objects.get(code='OP-03')
        self.assertEqual(expansion.name, 'Pillars of Strength')
        self.assertEqual(expansion.cards.count(), 2)


class ChartRangesTestCase(TestCase):
    """Menu range 3D/7D/14D/1M/3M/6M/1Y/5Y/ALL + variazioni % nel periodo."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.user = User.objects.create_user(username='rangetest', password='pw12345!')
        game = Game.objects.create(name='MTG')
        expansion = Expansion.objects.create(name='Test', code='TST', game=game)
        self.card = Card.objects.create(name='Snap', expansion=expansion, number='1', rarity='R')

        self.today = timezone.now().date()
        values = {6: 100, 4: 120, 2: 90, 0: 135}
        self.snapshots = []
        for days_ago, value in values.items():
            self.snapshots.append(ValueSnapshot.objects.create(
                owner=self.user,
                date=self.today - timedelta(days=days_ago),
                total_value=value,
            ))

    def test_parse_range_defaults_to_all(self):
        from cards.services import RANGES, parse_range
        self.assertEqual(parse_range(None), 'ALL')
        self.assertEqual(parse_range('7d'), '7D')
        self.assertEqual(parse_range('nonsense'), 'ALL')
        self.assertIn('3D', RANGES)
        self.assertNotIn('1D', RANGES)

    def test_build_chart_series_math(self):
        from cards.services import build_chart_series
        series = build_chart_series(self.snapshots, '7D')
        self.assertEqual(series['values'], [100.0, 120.0, 90.0, 135.0])
        self.assertEqual(series['relative'], [100.0, 120.0, 90.0, 135.0])
        self.assertAlmostEqual(series['change_pct'], 35.0, places=4)
        self.assertAlmostEqual(series['change_abs'], 35.0, places=4)

    def test_build_chart_series_filters_old_points_3d(self):
        from cards.services import build_chart_series
        # range 3D: inizia a oggi-3 giorni -> restano le rilevazioni di oggi-2 e oggi
        series = build_chart_series(self.snapshots, '3D')
        self.assertEqual(series['values'], [90.0, 135.0])
        self.assertEqual(series['relative'], [100.0, 150.0])
        self.assertAlmostEqual(series['change_pct'], 50.0, places=4)

    def test_home_renders_range_menu_and_stats(self):
        # un owned card da 135€ -> lo snapshot di oggi resta coerente
        OwnedCard.objects.create(owner=self.user, card=self.card, market_value=135, status='owned')

        self.client.login(username='rangetest', password='pw12345!')
        response = self.client.get(reverse('home'), {'range': '7D'})
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['current_range'], '7D')
        self.assertEqual(len(response.context['ranges']), 9)
        self.assertAlmostEqual(response.context['change_pct'], 35.0, places=4)
        self.assertAlmostEqual(response.context['current'], 135.0, places=2)
        self.assertEqual(response.context['relative'], [100.0, 120.0, 90.0, 135.0])


class CardSearchAPITestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='searchuser', password='pw12345!')
        game = Game.objects.create(name='Pokémon')
        exp = Expansion.objects.create(name='151', code='MEW', game=game)
        Card.objects.create(name='Charizard ex', expansion=exp, number='6', rarity='Special', image_url='http://x/p.png')
        Card.objects.create(name='Mew ex', expansion=exp, number='151', rarity='Special')
        Card.objects.create(name='Pikachu', expansion=exp, number='25', rarity='Common')

    def test_requires_login(self):
        response = self.client.get(reverse('card-search'), {'q': 'char'})
        self.assertEqual(response.status_code, 302)

    def test_empty_query_returns_no_results(self):
        self.client.login(username='searchuser', password='pw12345!')
        response = self.client.get(reverse('card-search'), {'q': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])

    def test_search_filters_by_name(self):
        self.client.login(username='searchuser', password='pw12345!')
        response = self.client.get(reverse('card-search'), {'q': 'char'})
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Charizard ex')
        self.assertEqual(results[0]['set_code'], 'MEW')
        self.assertEqual(results[0]['image_url'], 'http://x/p.png')

    def test_search_limits_to_20(self):
        game = Game.objects.create(name='Extra')
        exp = Expansion.objects.create(name='X', code='XXX', game=game)
        for i in range(25):
            Card.objects.create(name=f'Bulbasaur {i}', expansion=exp, number=str(i), rarity='C')
        self.client.login(username='searchuser', password='pw12345!')
        response = self.client.get(reverse('card-search'), {'q': 'bulba'})
        self.assertEqual(len(response.json()['results']), 20)


class CollectionPaginationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='paguser', password='pw12345!')
        game = Game.objects.create(name='MTG')
        self.exp = Expansion.objects.create(name='Test', code='TST', game=game)
        self.card = Card.objects.create(name='Carta Di Prova', expansion=self.exp, number='1', rarity='R')
        for i in range(30):
            OwnedCard.objects.create(owner=self.user, card=self.card, status='owned', market_value=i)

    def test_collection_is_paginated_by_24_in_flat_view(self):
        self.client.login(username='paguser', password='pw12345!')
        response = self.client.get(reverse('collection'), {'view': 'flat'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['is_flat'], True)
        self.assertEqual(len(response.context['owned_cards']), 24)
        self.assertEqual(response.context['total_count'], 30)

        response = self.client.get(reverse('collection'), {'view': 'flat', 'page': 2})
        self.assertEqual(len(response.context['owned_cards']), 6)

    def test_collection_grouped_by_game_by_default(self):
        self.client.login(username='paguser', password='pw12345!')
        response = self.client.get(reverse('collection'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['is_flat'], False)
        groups = response.context['cards_by_game']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['game'].name, 'MTG')
        self.assertEqual(groups[0]['count'], 30)

    def test_collection_grouped_section_is_capped(self):
        # 15 carte dello stesso gioco -> nel gruppo ne vengono mostrate al max 12
        self.client.login(username='paguser', password='pw12345!')
        response = self.client.get(reverse('collection'))
        group = response.context['cards_by_game'][0]
        self.assertEqual(group['count'], 30)
        self.assertEqual(len(group['cards']), 12)
        self.assertTrue(group['more'])

    def test_collection_filters_by_name(self):
        self.client.login(username='paguser', password='pw12345!')
        response = self.client.get(reverse('collection'), {'q': 'inesistente'})
        self.assertEqual(response.context['total_count'], 0)
        self.assertEqual(response.context['cards_by_game'], [])

    def test_collection_filters_by_game(self):
        self.client.login(username='paguser', password='pw12345!')
        other_game = Game.objects.create(name='Altro Gioco')
        exp = Expansion.objects.create(name='Altro', code='ALX', game=other_game)
        other = Card.objects.create(name='Altro', expansion=exp, number='1', rarity='C')
        OwnedCard.objects.create(owner=self.user, card=other, status='owned', market_value=999)

        response = self.client.get(reverse('collection'), {'game': other_game.id})
        self.assertEqual(response.context['total_count'], 1)
        self.assertEqual(len(response.context['cards_by_game']), 1)
        self.assertEqual(response.context['cards_by_game'][0]['game'].name, 'Altro Gioco')


class SnapshotRefreshTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='snapuser', password='pw12345!')
        game = Game.objects.create(name='MTG')
        exp = Expansion.objects.create(name='Test', code='TST', game=game)
        self.card = Card.objects.create(name='Snappy', expansion=exp, number='1', rarity='R')

    def test_create_owned_card_updates_today_snapshot(self):
        self.client.login(username='snapuser', password='pw12345!')
        response = self.client.post(reverse('collection-add'), {
            'card': self.card.pk,
            'card_type': 'raw',
            'condition': 'NM',
            'language': 'Italiano',
            'status': 'owned',
            'market_value': '50.00',
            'notes': '',
            'grading_company': '',
            'grade': '',
            'purchase_price': '',
        })
        self.assertEqual(response.status_code, 302)
        from django.utils import timezone
        snapshot = ValueSnapshot.objects.get(owner=self.user, date=timezone.now().date())
        self.assertEqual(float(snapshot.total_value), 50.0)

    def test_update_owned_card_updates_snapshot(self):
        owned = OwnedCard.objects.create(
            owner=self.user, card=self.card, status='owned', market_value=10
        )
        self.client.login(username='snapuser', password='pw12345!')
        response = self.client.post(reverse('collection-edit', args=[owned.pk]), {
            'card': self.card.pk,
            'card_type': 'raw',
            'condition': 'LP',
            'language': 'Italiano',
            'status': 'owned',
            'market_value': '77.00',
        })
        self.assertEqual(response.status_code, 302)
        from django.utils import timezone
        snapshot = ValueSnapshot.objects.get(owner=self.user, date=timezone.now().date())
        self.assertEqual(float(snapshot.total_value), 77.0)
        snapshot = ValueSnapshot.objects.get(owner=self.user, date=timezone.now().date())
        self.assertEqual(float(snapshot.total_value), 77.0)


class ImportScryfallCommandTestCase(TestCase):
    """Il comando di seed da Scryfall (API mockata) crea gioco/espansione/carte con immagini."""

    def test_import_creates_catalog_with_images(self):
        from unittest.mock import patch

        from django.core.management import call_command

        from cards.management.commands import import_scryfall

        sets_payload = {
            'object': 'list', 'has_more': False,
            'data': [
                {'code': 'one', 'name': 'Phyrexia: All Will Be One', 'released_at': '2023-02-10'},
            ],
        }
        cards_payload = {
            'object': 'list', 'has_more': False,
            'data': [
                {
                    'name': 'Against All Odds',
                    'collector_number': '1',
                    'rarity': 'R',
                    'image_uris': {'png': 'https://cards.scryfall.io/png/one.png'},
                },
                {
                    'name': 'Crawling Chorus',
                    'collector_number': '8',
                    'rarity': 'C',
                    'card_faces': [
                        {'image_uris': {'png': 'https://cards.scryfall.io/png/two.png'}},
                    ],
                },
            ],
        }

        def fake_fetch_json(url):
            if 'sets' in url:
                return sets_payload
            return cards_payload

        with patch.object(import_scryfall, 'fetch_json', side_effect=fake_fetch_json):
            call_command('import_scryfall', sets='one', sleep=0, verbosity=0)

        game = Game.objects.get(name='Magic: The Gathering')
        expansion = Expansion.objects.get(code='ONE', game=game)
        self.assertEqual(expansion.name, 'Phyrexia: All Will Be One')
        self.assertEqual(expansion.cards.count(), 2)

        c1 = expansion.cards.get(number='1')
        self.assertEqual(c1.image_url, 'https://cards.scryfall.io/png/one.png')
        c2 = expansion.cards.get(number='8')
        # carta bifacciale: immagine presa da card_faces[0]
        self.assertEqual(c2.image_url, 'https://cards.scryfall.io/png/two.png')

    def test_import_is_idempotent(self):
        from unittest.mock import patch

        from django.core.management import call_command

        from cards.management.commands import import_scryfall

        sets_payload = {
            'object': 'list', 'has_more': False,
            'data': [{'code': 'neo', 'name': 'Kamigawa Neon Dynasty', 'released_at': '2022-02-18'}],
        }
        cards_payload = {
            'object': 'list', 'has_more': False,
            'data': [{'name': 'Jin-Gitaxias', 'collector_number': '73', 'rarity': 'R',
                      'image_uris': {'png': 'https://x/neo.png'}}],
        }

        def fake(url):
            return sets_payload if 'sets' in url else cards_payload

        with patch.object(import_scryfall, 'fetch_json', side_effect=fake):
            call_command('import_scryfall', sets='neo', sleep=0, verbosity=0)
            call_command('import_scryfall', sets='neo', sleep=0, verbosity=0)

        expansion = Expansion.objects.get(code='NEO')
        self.assertEqual(expansion.cards.count(), 1)  # nessun duplicato
        expansion = Expansion.objects.get(code='NEO')
        self.assertEqual(expansion.cards.count(), 1)  # nessun duplicato


class ImportPokemonCommandTestCase(TestCase):
    def test_import_creates_pokemon_set(self):
        from unittest.mock import patch

        from django.core.management import call_command

        from cards.management.commands import import_pokemon

        cards_payload = {
            'data': [
                {
                    'name': 'Armarouge', 'number': '043', 'rarity': 'Rare',
                    'set': {'id': 'sv1', 'name': 'Scarlet & Violet', 'releaseDate': '2023/03/31'},
                    'images': {'large': 'https://images.pokemontcg.io/sv1/43_hires.png',
                               'small': 'https://images.pokemontcg.io/sv1/43.png'},
                },
            ],
            'page': 1, 'pageSize': 250, 'totalCount': 1,
        }

        def fake(url, timeout=30, extra_headers=None, retries=3):
            return cards_payload

        with patch.object(import_pokemon, 'fetch_json', side_effect=fake):
            call_command('import_pokemon', sets='sv1', sleep=0, verbosity=0)

        game = Game.objects.get(name='Pokémon')
        expansion = Expansion.objects.get(code='SV1', game=game)
        self.assertEqual(expansion.name, 'Scarlet & Violet')
        card = expansion.cards.get(number='043')
        self.assertEqual(card.name, 'Armarouge')
        self.assertEqual(card.rarity, 'Rare')
        self.assertEqual(card.image_url, 'https://images.pokemontcg.io/sv1/43_hires.png')


class ImportYgoCommandTestCase(TestCase):
    def test_import_creates_ygo_set(self):
        from unittest.mock import patch

        from django.core.management import call_command

        from cards.management.commands import import_ygo

        cardinfo_payload = {
            'data': [
                {
                    'name': 'Dark Magician',
                    'card_sets': [
                        {'set_name': 'Legend of Blue Eyes White Dragon',
                         'set_code': 'LOB-EN000', 'set_rarity_code': '(UR)'},
                    ],
                    'card_images': [
                        {'image_url': 'https://images.ygoprodeck.com/images/cards/46986414.jpg'},
                    ],
                },
            ],
        }

        with patch.object(import_ygo, 'fetch_json', return_value=cardinfo_payload):
            call_command('import_ygo', sets='Legend of Blue Eyes White Dragon', verbosity=0)

        game = Game.objects.get(name='Yu-Gi-Oh!')
        expansion = Expansion.objects.get(code='LOB', game=game)
        card = expansion.cards.get(number='000')
        self.assertEqual(card.name, 'Dark Magician')
        self.assertEqual(card.image_url, 'https://images.ygoprodeck.com/images/cards/46986414.jpg')
        self.assertEqual(expansion.cards.count(), 1)
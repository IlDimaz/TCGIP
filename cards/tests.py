from django.test import TestCase
from django.urls import reverse
from users.models import User
from cards.models import Game, Expansion, Card, OwnedCard


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
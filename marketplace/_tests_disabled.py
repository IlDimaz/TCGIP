from django.test import TestCase
from django.urls import reverse
from users.models import User
from cards.models import Game, Expansion, Card, OwnedCard
from marketplace.models import Listing, Offer, Transaction, Review


class MarketplaceFlowTestCase(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username='seller', password='testpass123')
        self.buyer = User.objects.create_user(username='buyer', password='testpass123')

        game = Game.objects.create(name='Pokémon TCG')
        expansion = Expansion.objects.create(name='Base', code='BASE', game=game)
        card = Card.objects.create(name='Charizard', expansion=expansion, number='4', rarity='Rare')

        self.owned_card = OwnedCard.objects.create(
            card=card, owner=self.seller, status='owned'
        )
        self.listing = Listing.objects.create(
            owner=self.seller, owned_card=self.owned_card, price=100
        )

    def test_marketplace_list_accessible_without_login(self):
        # Il marketplace è pubblico, chiunque deve poterlo sfogliare
        response = self.client.get(reverse('marketplace-list'))
        self.assertEqual(response.status_code, 200)

    def test_offer_requires_login(self):
        response = self.client.post(
            reverse('offer-create', args=[self.listing.pk]),
            {'amount': 80, 'message': 'Offerta di prova'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Offer.objects.exists())

    def test_buyer_can_create_offer(self):
        self.client.login(username='buyer', password='testpass123')
        self.client.post(
            reverse('offer-create', args=[self.listing.pk]),
            {'amount': 80, 'message': 'Offerta di prova'}
        )
        self.assertTrue(Offer.objects.filter(buyer=self.buyer, amount=80).exists())

    def test_non_owner_cannot_accept_offer(self):
        # buyer prova ad accettare la propria stessa offerta: non è il turno suo
        offer = Offer.objects.create(
            listing=self.listing, buyer=self.buyer, amount=80,
            proposed_by='buyer', status='pending'
        )
        self.client.login(username='buyer', password='testpass123')
        self.client.post(reverse('offer-accept', args=[offer.pk]))
        offer.refresh_from_db()
        # Non cambia lo stato dell'offerta se l'azione non è autorizzata
        self.assertEqual(offer.status, 'pending')

    def test_seller_can_accept_offer_and_creates_transaction(self):
        offer = Offer.objects.create(
            listing=self.listing, buyer=self.buyer, amount=80,
            proposed_by='buyer', status='pending'
        )
        self.client.login(username='seller', password='testpass123')
        self.client.post(reverse('offer-accept', args=[offer.pk]))

        offer.refresh_from_db()


    def test_transaction_complete_transfers_ownership(self):
        offer = Offer.objects.create(
            listing=self.listing, buyer=self.buyer, amount=80,
            proposed_by='buyer', status='accepted'
        )
        transaction = Transaction.objects.create(
            listing=self.listing, offer=offer,
            buyer=self.buyer, seller=self.seller, price=80, status='pending'
        )
        self.client.login(username='seller', password='testpass123')
        
        self.client.post(
            reverse('transaction-complete', args=[transaction.pk]),
            {'carrier': 'brt'}
        )

        transaction.refresh_from_db()
        self.owned_card.refresh_from_db()
        self.assertEqual(transaction.status, 'completed')
        self.assertEqual(self.owned_card.status, 'sold')
        # Verifica che l'acquirente abbia ricevuto la propria copia
        self.assertTrue(
            OwnedCard.objects.filter(owner=self.buyer, card=self.owned_card.card).exists()
        )
        self.client.login(username='seller', password='testpass123')
        response = self.client.get(reverse('collection'))
        self.assertNotContains(response, self.owned_card.card.name)
        response = self.client.get(reverse('sold-cards'))
        self.assertEqual(response.context['total_profit'], 80)


class ReviewFlowTestCase(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username='seller', password='testpass123')
        self.buyer = User.objects.create_user(username='buyer', password='testpass123')

        game = Game.objects.create(name='Pokémon TCG')
        expansion = Expansion.objects.create(name='Base', code='BASE', game=game)
        card = Card.objects.create(name='Charizard', expansion=expansion, number='4', rarity='Rare')
        owned_card = OwnedCard.objects.create(card=card, owner=self.seller, status='owned')
        listing = Listing.objects.create(owner=self.seller, owned_card=owned_card, price=100)
        offer = Offer.objects.create(
            listing=listing, buyer=self.buyer, amount=100,
            proposed_by='buyer', status='accepted'
        )
        self.transaction = Transaction.objects.create(
            listing=listing, offer=offer,
            buyer=self.buyer, seller=self.seller, price=100, status='completed'
        )

    def test_buyer_can_review_completed_transaction(self):
        self.client.login(username='buyer', password='testpass123')
        self.client.post(reverse('review-create', args=[self.transaction.pk]), {
            'rating': 5, 'comment': 'Ottimo venditore'
        })
        self.assertTrue(Review.objects.filter(transaction=self.transaction, rating=5).exists())

    def test_seller_cannot_review_own_transaction(self):
        # Solo il buyer può recensire, non il seller
        self.client.login(username='seller', password='testpass123')
        self.client.post(reverse('review-create', args=[self.transaction.pk]), {
            'rating': 1, 'comment': 'Tentativo non autorizzato'
        })
        self.assertFalse(Review.objects.exists())

    def test_cannot_review_same_transaction_twice(self):
        self.client.login(username='buyer', password='testpass123')
        self.client.post(reverse('review-create', args=[self.transaction.pk]), {
            'rating': 5, 'comment': 'Prima recensione'
        })
        self.client.post(reverse('review-create', args=[self.transaction.pk]), {
            'rating': 1, 'comment': 'Seconda recensione'
        })
        # Deve essercene solo una
        self.assertEqual(Review.objects.filter(transaction=self.transaction).count(), 1)

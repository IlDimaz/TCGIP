from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from cards.models import OwnedCard


class Listing(models.Model):
    LISTING_TYPE_CHOICES = [
        ('fixed', 'Compra Subito'),
        ('auction', 'Asta'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='listings')
    owned_card = models.ForeignKey(OwnedCard, on_delete=models.CASCADE, related_name='listings')
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    description = models.TextField(blank=True)
    shipping_available = models.BooleanField(default=False)
    pickup_available = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    listing_type = models.CharField(max_length=10, choices=LISTING_TYPE_CHOICES, default='fixed')
    auction_end = models.DateTimeField(null=True, blank=True)
    auction_closed = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.owned_card.card.name} - {self.price}€'

    def highest_bid(self):
        """Restituisce l'offerta più alta per le aste."""
        return self.offers.filter(offer_type='bid').order_by('-amount').first()

    def close_auction_if_expired(self):
        """
        Chiude automaticamente l'asta se il tempo è scaduto e assegna
        la carta all'offerta/rilancio vincente.
        """
        if self.listing_type != 'auction' or not self.auction_end:
            return
        if timezone.now() < self.auction_end or self.auction_closed:
            return

        closed = Listing.objects.filter(pk=self.pk, auction_closed=False).update(auction_closed=True)
        if not closed:
            return
        self.auction_closed = True

        winning_bid = self.highest_bid()
        if winning_bid:
            # Import dinamico per evitare importazioni circolari con views.py
            from .views import create_transaction_from_offer
            create_transaction_from_offer(winning_bid)


class Offer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'In attesa'),
        ('accepted', 'Accettata'),
        ('rejected', 'Rifiutata'),
    ]

    PROPOSED_BY_CHOICES = [
        ('buyer', 'Acquirente'),
        ('seller', 'Venditore'),
    ]

    OFFER_TYPE_CHOICES = [
        ('offer', 'Offerta'),
        ('message', 'Messaggio'),
        ('bid', 'Rilancio'),
    ]

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='offers')
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='offers_made')
    offer_type = models.CharField(max_length=10, choices=OFFER_TYPE_CHOICES, default='offer')
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    message = models.TextField(blank=True)
    proposed_by = models.CharField(max_length=10, choices=PROPOSED_BY_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    parent_offer = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='counter_offers')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.offer_type in ('offer', 'bid'):
            if self.amount is None or self.amount <= Decimal('0.00'):
                raise ValidationError('L\'importo dell\'offerta deve essere maggiore di 0€.')

        if self.offer_type == 'bid':
            current_highest = self.listing.highest_bid()
            min_required = current_highest.amount if current_highest else self.listing.price
            if self.amount <= min_required:
                raise ValidationError(f'Il rilancio deve essere superiore a {min_required}€.')

    def __str__(self):
        if self.offer_type == 'message':
            return f'Messaggio su {self.listing}'
        if self.offer_type == 'bid':
            return f'Rilancio {self.amount}€ su {self.listing}'
        return f'Offerta {self.amount}€ su {self.listing}'

    def latest_in_chain(self):
        """
        Percorre la catena di risposte (counter_offers) fino a trovare
        l'ultimo messaggio/offerta inviato nel thread.
        """
        current = self
        while current.counter_offers.exists():
            current = current.counter_offers.order_by('-created_at').first()
        return current

    def is_user_turn(self, user):
        """Verifica se tocca all'utente corrente rispondere all'offerta/controproposta."""
        is_seller_turn = self.proposed_by == 'buyer' and self.listing.owner == user
        is_buyer_turn = self.proposed_by == 'seller' and self.buyer == user
        return is_seller_turn or is_buyer_turn


class Transaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'In attesa'),
        ('completed', 'Completata'),
        ('cancelled', 'Annullata'),
    ]

    CARRIER_CHOICES = [
        ('brt', 'BRT'),
        ('dhl', 'DHL'),
        ('poste', 'Poste Italiane'),
        ('gls', 'GLS'),
    ]

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='transactions')
    offer = models.OneToOneField(Offer, on_delete=models.CASCADE, related_name='transaction')
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchases')
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sales')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    carrier = models.CharField(max_length=10, choices=CARRIER_CHOICES, blank=True)
    shipping_cost = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Transazione #{self.pk} - {self.status}'

    def estimate_shipping_cost(self):
        """Calcola la stima dei costi di spedizione basandosi sul valore della carta."""
        if self.price >= 300:
            return Decimal('20.00')
        elif self.price >= 100:
            return Decimal('10.00')
        return Decimal('4.00')

    @property
    def total_price(self):
        """Prezzo carta + spedizione: il vero costo sostenuto dal buyer.
        Usato in template e contabilità invece di ripetere il calcolo
        price + shipping_cost ovunque serva."""
        if self.shipping_cost is None:
            return self.price  # ancora pending, spedizione non scelta
        return self.price + self.shipping_cost

    @transaction.atomic
    def complete(self, carrier):
        """
        MOTORE DELLA CONTABILITÀ E DEL TRASFERIMENTO CARTA:
        1. Imposta corriere, spese di spedizione e stato completato.
        2. Aggiorna la carta del VENDITORE (status='sold', sale_price, sold_date) -> ENTRATA.
        3. Crea la carta per l'ACQUIRENTE (status='owned', purchase_price) -> USCITA.
        4. Rimuove l'inserzione dal mercato (is_active=False).
        """
        self.carrier = carrier
        self.shipping_cost = self.estimate_shipping_cost()
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

        old_card = self.listing.owned_card
        old_card.status = 'sold'
        old_card.sale_price = self.price
        old_card.sold_date = timezone.now().date()
        old_card.save()

        OwnedCard.objects.create(
            card=old_card.card,
            owner=self.buyer,
            image=old_card.image,
            card_type=old_card.card_type,
            condition=old_card.condition,
            grading_company=old_card.grading_company,
            grade=old_card.grade,
            language=old_card.language,
            status='owned',
            purchase_price=self.total_price,  # esempio riutilizzo della funzione invece di ripetere il calcolo
        )

        self.listing.is_active = False
        self.listing.save()


class Review(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Recensione {self.rating}/5 su {self.transaction}'
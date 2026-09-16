from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import ListingForm, MessageForm, OfferForm, ReviewForm, ListingEditForm
from .models import Listing, Offer, Transaction


class ListingListView(ListView):
    model = Listing
    template_name = 'marketplace/listing_list.html'
    context_object_name = 'listings'

    def get_queryset(self):
        # Il proprietario vede i propri annunci solo nella pagina dedicata.
        listings = Listing.objects.filter(is_active=True).select_related('owned_card__card__expansion')
        if self.request.user.is_authenticated:
            listings = listings.exclude(owner=self.request.user)
        return listings


class ListingDetailView(DetailView):
    model = Listing
    template_name = 'marketplace/listing_detail.html'
    context_object_name = 'listing'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # Chiude l'asta prima di mostrarne dettagli o azioni disponibili.
        obj.close_auction_if_expired()

        if self.request.user.is_authenticated:
            # Segna come letti soltanto i messaggi ricevuti dall'utente corrente.
            is_seller = self.request.user == obj.owner
            Offer.objects.filter(
                listing=obj, offer_type='message', is_read=False
            ).exclude(
                proposed_by='seller' if is_seller else 'buyer'
            ).update(is_read=True)

        return obj

class ListingCreateView(LoginRequiredMixin, CreateView):
    model = Listing
    form_class = ListingForm
    template_name = 'marketplace/listing_form.html'
    success_url = reverse_lazy('marketplace-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Il form mostra soltanto le carte vendibili dell'utente.
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class OfferCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        listing = get_object_or_404(Listing, pk=pk, is_active=True)
        form = OfferForm(request.POST)

        if form.is_valid():
            offer = form.save(commit=False)
            offer.listing = listing
            offer.buyer = request.user
            offer.proposed_by = 'buyer'
            offer.offer_type = 'offer'
            offer.save()
            messages.success(request, 'Offerta inviata al venditore.')
        else:
            messages.error(request, 'Inserisci un importo valido (maggiore di 0€).')
        return redirect('marketplace-detail', pk=pk)


@transaction.atomic
def create_transaction_from_offer(offer):
    # Riserva l'annuncio e crea la vendita in attesa della spedizione.
    offer.status = 'accepted'
    offer.save()

    # Il lock evita che due richieste simultanee riservino la stessa carta.
    listing = get_object_or_404(
        Listing.objects.select_for_update(), pk=offer.listing_id, is_active=True
    )
    listing.is_active = False
    listing.save()

    return Transaction.objects.create(
        listing=listing,
        offer=offer,
        buyer=offer.buyer,
        seller=listing.owner,
        price=offer.amount,
    )

#accettazione offerta e gestione casi particolari
class OfferAcceptView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Una vecchia offerta pending non può essere accettata dopo un'altra vendita.
        offer = get_object_or_404(
            Offer, pk=pk, status='pending', offer_type='offer', listing__is_active=True
        )

        if offer.listing.listing_type == 'auction':
            messages.error(request, 'Non puoi accettare manualmente un\'offerta durante un\'asta. L\'asta deve scadere.')
            return redirect('marketplace-detail', pk=offer.listing.pk)

        if not offer.is_user_turn(request.user):
            messages.error(request, 'Non puoi accettare questa offerta.')
            return redirect('marketplace-detail', pk=offer.listing.pk)

        create_transaction_from_offer(offer)
        messages.success(request, 'Offerta accettata. Ora scegli il corriere per completare la vendita.')
        return redirect('marketplace-detail', pk=offer.listing.pk)

#idem ma rifiuto offerta
class OfferRejectView(LoginRequiredMixin, View):
    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk, status='pending', offer_type='offer')

        if not offer.is_user_turn(request.user):
            messages.error(request, 'Non puoi rifiutare questa offerta.')
            return redirect('marketplace-detail', pk=offer.listing.pk)

        offer.status = 'rejected'
        offer.save()
        messages.info(request, 'Offerta rifiutata.')
        return redirect('marketplace-detail', pk=offer.listing.pk)

#gestione scambio di proposte tra buyer e seller
class CounterOfferView(LoginRequiredMixin, View):
    def post(self, request, pk):
        old_offer = get_object_or_404(Offer, pk=pk, status='pending', offer_type='offer')

        if not old_offer.is_user_turn(request.user):
            messages.error(request, 'Non puoi controproporre su questa offerta.')
            return redirect('marketplace-detail', pk=old_offer.listing.pk)

        form = OfferForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                old_offer.status = 'rejected'
                old_offer.save()

                is_seller = old_offer.listing.owner == request.user
                new_offer = form.save(commit=False)
                new_offer.listing = old_offer.listing
                new_offer.buyer = old_offer.buyer
                new_offer.proposed_by = 'seller' if is_seller else 'buyer'
                new_offer.parent_offer = old_offer
                new_offer.status = 'pending'
                new_offer.offer_type = 'offer'
                new_offer.save()

            messages.success(request, 'Controproposta inviata.')
        return redirect('marketplace-detail', pk=old_offer.listing.pk)

#registrazione rilanci asta
class BidCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        listing = get_object_or_404(Listing, pk=pk, listing_type='auction', is_active=True)
        listing.close_auction_if_expired()
        if listing.auction_closed:
            messages.error(request, 'Asta già conclusa.')
            return redirect('marketplace-detail', pk=pk)

        instance = Offer(listing=listing, buyer=request.user, proposed_by='buyer', offer_type='bid')
        form = OfferForm(request.POST, instance=instance)

        if form.is_valid():
            form.save()
            messages.success(request, 'Rilancio registrato.')
        else:
            messages.error(request, 'Rilancio non valido. Deve superare l\'offerta attuale.')
        return redirect('marketplace-detail', pk=pk)


class MessageCreateView(LoginRequiredMixin, View):
    """Solo per aprire un NUOVO thread (bottone 'Contatta'). 
    Le risposte,sia da buyer che da seller, passano sempre da MessageReplyView."""
    def post(self, request, pk):
        listing = get_object_or_404(Listing, pk=pk, is_active=True)
        msg_text = request.POST.get('message')

        if not msg_text:
            messages.error(request, 'Inserisci un messaggio valido.')
            return redirect('marketplace-detail', pk=pk)

        Offer.objects.create(
            listing=listing,
            buyer=request.user,
            message=msg_text,
            proposed_by='buyer',
            offer_type='message',
        )
        messages.success(request, 'Messaggio inviato al venditore.')
        return redirect('marketplace-detail', pk=pk)


class MessageReplyView(LoginRequiredMixin, View):
    """Risposta nel thread, sia da buyer che da seller. 
    Unico punto d'ingresso per continuare una conversazione già aperta."""
    def post(self, request, pk):
        parent = get_object_or_404(Offer, pk=pk)
        listing = parent.listing
        thread_buyer = parent.buyer

        is_seller = listing.owner == request.user
        is_buyer = thread_buyer == request.user
        if not (is_seller or is_buyer):
            messages.error(request, 'Non puoi rispondere a questo thread.')
            return redirect('marketplace-detail', pk=listing.pk)

        instance = Offer(
            listing=listing,
            buyer=thread_buyer,
            offer_type='message',
            proposed_by='seller' if is_seller else 'buyer',
            parent_offer=parent.latest_in_chain(),
        )
        form = MessageForm(request.POST, instance=instance)

        if form.is_valid():
            form.save()
            messages.success(request, 'Messaggio inviato.')
        else:
            messages.error(request, 'Errore nell\'invio del messaggio.')
        return redirect('marketplace-detail', pk=listing.pk)


class TransactionCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        transaction_obj = get_object_or_404(Transaction, pk=pk, seller=request.user, status='pending')

        carrier = request.POST.get('carrier')
        if carrier not in dict(Transaction.CARRIER_CHOICES):
            messages.error(request, 'Seleziona un corriere valido.')
            return redirect('marketplace-detail', pk=transaction_obj.listing.pk)

        transaction_obj.complete(carrier=carrier)
        messages.success(request, 'Transazione completata. La carta è stata trasferita.')
        return redirect('marketplace-detail', pk=transaction_obj.listing.pk)


class MyPurchasesView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'marketplace/my_purchases.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        return Transaction.objects.filter(buyer=self.request.user).order_by('-created_at')


class MySalesView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'marketplace/my_sales.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        return Transaction.objects.filter(seller=self.request.user).order_by('-created_at')


class ReviewCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        transaction_obj = get_object_or_404(Transaction, pk=pk, buyer=request.user, status='completed')

        if hasattr(transaction_obj, 'review'):
            messages.error(request, 'Hai già recensito questa transazione.')
            return redirect('my-purchases')

        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.transaction = transaction_obj
            review.save()
            messages.success(request, 'Recensione pubblicata.')
        return redirect('my-purchases')

class BuyNowView(LoginRequiredMixin, View):
    """Acquisto diretto al prezzo pieno, solo per annunci a prezzo fisso.
    Crea un'offerta al prezzo esatto e la accetta subito, riusando
    create_transaction_from_offer - stesso flusso di un'offerta accettata
    manualmente, solo senza passare dalla negoziazione."""

    def post(self, request, pk):
        listing = get_object_or_404(Listing, pk=pk, is_active=True, listing_type='fixed')

        if request.user == listing.owner:
            messages.error(request, 'Non puoi comprare il tuo stesso annuncio.')
            return redirect('marketplace-detail', pk=pk)

        offer = Offer.objects.create(
            listing=listing, buyer=request.user, amount=listing.price,
            proposed_by='buyer', offer_type='offer', status='pending'
        )
        create_transaction_from_offer(offer)
        messages.success(request, 'Acquisto registrato! Il venditore completerà la spedizione a breve.')
        return redirect('marketplace-detail', pk=pk)

class MyListingsView(LoginRequiredMixin, ListView):
    # Raccoglie tutte le inserzioni dell'utente, incluse quelle concluse.
    model = Listing
    template_name = 'marketplace/my_listings.html'
    context_object_name = 'listings'

    def get_queryset(self):
        return Listing.objects.filter(owner=self.request.user).select_related('owned_card__card__expansion').order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Separa gli annunci nelle due righe della pagina.
        listings = list(context['listings'])
        groups = [
            {'title': 'Inserzioni attive', 'listings': [listing for listing in listings if listing.is_active]},
            {'title': 'Vendute / non attive', 'listings': [listing for listing in listings if not listing.is_active]},
        ]
        context['listing_groups'] = [group for group in groups if group['listings']]
        return context


class ListingEditView(LoginRequiredMixin, UpdateView):
    model = Listing
    form_class = ListingEditForm
    template_name = 'marketplace/listing_edit.html'
    success_url = reverse_lazy('my-listings')

    def get_queryset(self):
        # Puoi modificare solo le TUE inserzioni, non quelle altrui
        return Listing.objects.filter(owner=self.request.user)

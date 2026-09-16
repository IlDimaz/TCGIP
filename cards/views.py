import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.utils import timezone
from django.db.models import Sum, Q
from itertools import groupby
from .models import OwnedCard, Expansion, Card, ValueSnapshot, Game
from .forms import CSVImportForm, PersonalCSVImportForm, OwnedCardForm
from marketplace.models import Offer, Transaction


# Se loggato, mostra offerte e andamento della collezione
def home(request):
    if not request.user.is_authenticated:
        games = Game.objects.exclude(logo='')[:4]
        return render(request, 'landing.html', {'games': games})

    #se loggato creo context con quello da mostrare
    context = {}

    context['pending_offers'] = Offer.objects.filter(
        listing__owner=request.user, status='pending', offer_type='offer'
    ).select_related('listing', 'buyer')

    message_roots = Offer.objects.filter(
        offer_type='message', parent_offer__isnull=True
    ).filter(
        Q(buyer=request.user) | Q(listing__owner=request.user)
    ).select_related('listing', 'buyer') #mostro solo gli ultimi per non intasare

    unread_messages = []
    for root in message_roots:
        latest = root.latest_in_chain()  # notifico solo l'ultimo mess
        if latest.is_read:
            continue
        is_recipient = (
            (latest.proposed_by == 'buyer' and root.listing.owner == request.user) or  # il messaggio è scritto da me o no?
            (latest.proposed_by == 'seller' and root.buyer == request.user)
        )
        if is_recipient:
            unread_messages.append(latest)
    context['unread_messages'] = unread_messages

    context['pending_sales'] = Transaction.objects.filter(
        seller=request.user, status='pending'
    ).select_related('listing', 'buyer')

    context['pending_purchases'] = Transaction.objects.filter(
        buyer=request.user, status='pending'
    ).select_related('listing', 'seller')

    today = timezone.now().date()  # data
    total = OwnedCard.objects.filter(owner=request.user, status='owned').aggregate(total=Sum('market_value'))['total'] or 0  # tot collezione

    ValueSnapshot.objects.get_or_create(  # get or create, crea valore se non esiste
        owner=request.user, date=today,
        defaults={'total_value': total}
    )
    snapshots = ValueSnapshot.objects.filter(owner=request.user).order_by('date')
    # valori per plottare
    context['chart_labels'] = [s.date.strftime('%d/%m') for s in snapshots]  # del tipo   2026-08-01 → "01/08"
    context['chart_values'] = [float(s.total_value) for s in snapshots]  # list comprehension valori
    return render(request, 'home.html', context)


# Riutilizzato dalle view che devono operare soltanto sulle carte del proprietario.
class OwnerRequiredMixin:
    # Filtra il queryset per mostrare solo gli oggetti dell'utente loggato (owner)
    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


# Carte raggruppate per gioco (get_context_data), usato dal template per le sezioni
class CollectionListView(LoginRequiredMixin, ListView):
    model = OwnedCard
    template_name = 'cards/collection_list.html'
    context_object_name = 'owned_cards'

    def get_queryset(self):
        # status='owned': esclude le carte vendute, che stanno in un'altra view
        return OwnedCard.objects.filter(
            owner=self.request.user, status='owned'
        ).select_related('card__expansion__game')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # groupby richiede dati già ordinati per la stessa chiave, quindi li riordino con sorted() prima
        cards = sorted(context['owned_cards'], key=lambda c: c.card.expansion.game.name)
        # trasforma la lista piatta in un dict {nome_gioco: [carte]} per il template, così da essere divise per gioco
        context['cards_by_game'] = {
            game_name: list(group)
            for game_name, group in groupby(cards, key=lambda c: c.card.expansion.game.name)
        }
        return context


# owner assegnato in form_valid, mai disponibile come campo del form, si è automaticamente proprietari della carta che si crea salvo cessione
class OwnedCardCreateView(LoginRequiredMixin, CreateView):
    model = OwnedCard
    form_class = OwnedCardForm
    template_name = 'cards/collection_form.html'
    success_url = reverse_lazy('collection')


    def form_valid(self, form):
        form.instance.owner = self.request.user #imposto automaticamente il valore per garantire il funzionamento
        return super().form_valid(form)


# Aggiorna copia fisica
class OwnedCardUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    # OwnerRequiredMixin filtra il queryset: non si può modificare una carta altrui, anche sapendo l'id nel url
    model = OwnedCard
    form_class = OwnedCardForm
    template_name = 'cards/collection_form.html'
    success_url = reverse_lazy('collection')


# Elimina dietro conferma
class OwnedCardDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    model = OwnedCard
    template_name = 'cards/collection_confirm_delete.html'
    success_url = reverse_lazy('collection')


# Calcola guadagno/perdita per carta e totale
class SoldCardsListView(LoginRequiredMixin, ListView):
    model = OwnedCard
    template_name = 'cards/sold_list.html'
    context_object_name = 'sold_cards'

    def get_queryset(self):
        return OwnedCard.objects.filter(
            owner=self.request.user, status='sold'
        ).order_by('-sold_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cards_with_diff = []
        total_profit = 0
        for card in context['sold_cards']:
            diff = None
            diff_percent = None
            if card.sale_price is not None: #per evitare errori
                purchase_price = card.purchase_price or 0
                diff = card.sale_price - purchase_price
                total_profit += diff
                if purchase_price:
                    # percentuale calcolata solo se purchase_price != 0 ( ZeroDivisionError)
                    diff_percent = (diff / purchase_price) * 100

            cards_with_diff.append({
                'card': card,
                'diff': diff,
                'diff_percent': diff_percent,
            })

        context['cards_with_diff'] = cards_with_diff
        context['total_profit'] = total_profit
        return context


@staff_member_required
# Import catalogo versione solo staff
def import_cards_view(request):
    if request.method == 'POST':
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            game = form.cleaned_data['game']
            expansion = form.cleaned_data['expansion']
            new_expansion_name = form.cleaned_data['new_expansion_name'].strip() if form.cleaned_data.get('new_expansion_name') else ''
            new_expansion_code = form.cleaned_data.get('new_expansion_code', '').strip().upper()

            if not expansion:
                expansion, _ = Expansion.objects.get_or_create(
                    name=new_expansion_name,
                    game=game,
                    defaults={'code': new_expansion_code}
                )

            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)

            created_count = 0
            skipped_count = 0

            for row in reader:
                # supporta due formati di CSV diversi in base ai 2 siti che ho trovato
                name = row.get('Name') or row.get('name', '')
                number = row.get('Number') or row.get('extNumber', '')
                rarity = row.get('Rarity') or row.get('extRarity', '')

                if not name or not number: #salto quello che non riesco a caricare
                    skipped_count += 1
                    continue

                card, created = Card.objects.get_or_create(
                    name=name,
                    number=number,
                    expansion=expansion,
                    defaults={'rarity': rarity},
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

            messages.success(
                request,
                f'Import completato in "{expansion.name}": {created_count} carte create, {skipped_count} già esistenti.'
            )
            return redirect('import-cards')
    else:
        form = CSVImportForm()

    return render(request, 'cards/import_csv.html', {'form': form})


# Le carte devono già esistere nel catalogo: solo get() puro, non get_or_create, csv personale
class ImportPersonalCollectionView(LoginRequiredMixin, View):
    def get(self, request):
        form = PersonalCSVImportForm()
        return render(request, 'cards/import_personal_csv.html', {'form': form})

    def post(self, request):
        # Converte le righe CSV in copie fisiche della collezione utente.
        form = PersonalCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)

            created_count = 0
            skipped_rows = []

            for row in reader:
                try:
                    # get() puro, non get_or_create: qui NON si crea catalogo,
                    # la carta deve già esistere (import personale, non import catalogo)
                    expansion = Expansion.objects.get(code=row['SetCode'])
                    card = Card.objects.get(expansion=expansion, number=row['Number'])
                except (Expansion.DoesNotExist, Card.DoesNotExist):
                    # riga saltata invece di far fallire tutto l'import, come poc'anzi
                    skipped_rows.append(
                        f"{row.get('Name', '?')} ({row.get('SetCode', '?')} {row.get('Number', '?')}) - carta non trovata nel catalogo"
                    )
                    continue

                OwnedCard.objects.create(
                    card=card,
                    owner=request.user,
                    card_type=row.get('CardType', 'raw') or 'raw',
                    condition=row.get('Condition', ''),
                    grading_company=row.get('GradingCompany', ''),
                    grade=row.get('Grade') or None,
                    purchase_price=row.get('PurchasePrice') or None,
                    market_value=row.get('MarketValue') or None,
                    language=row.get('Language', 'Italian') or 'Italian',
                    notes=row.get('Notes', ''),
                    status='owned',
                )
                created_count += 1

            messages.success(request, f'Import completato: {created_count} carte aggiunte alla tua collezione.')
            if skipped_rows:
                # mostra solo le prime 5 righe saltate per non intasare il messaggio
                messages.warning(
                    request,
                    f'{len(skipped_rows)} righe saltate (carta non trovata nel catalogo): ' + '; '.join(skipped_rows[:5])
                )

            return redirect('collection')

        return render(request, 'cards/import_personal_csv.html', {'form': form})


class ExportCollectionView(LoginRequiredMixin, View):
    def get(self, request):
        # Esporta sia carte possedute sia vendute per un backup completo.
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="my_collection.csv"'

        writer = csv.writer(response) # csv.writer scrive direttamente sulla HttpResponse, evitiamo l'utilizzo di file temporanei
        writer.writerow([
            'SetCode', 'Number', 'Name', 'CardType', 'Condition',
            'GradingCompany', 'Grade', 'PurchasePrice', 'MarketValue',
            'Language', 'Notes', 'Status', 'SalePrice', 'SoldDate'
        ])

        owned_cards = OwnedCard.objects.filter(owner=request.user).select_related('card', 'card__expansion')

        for oc in owned_cards:
            writer.writerow([
                oc.card.expansion.code,
                oc.card.number,
                oc.card.name,
                oc.card_type,
                oc.condition,
                oc.grading_company,
                oc.grade or '',
                oc.purchase_price or '',
                oc.market_value or '',
                oc.language,
                oc.notes,
                oc.status,
                oc.sale_price or '',
                oc.sold_date or '',
            ])

        return response

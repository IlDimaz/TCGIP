import csv
from datetime import timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import CSVImportForm, OwnedCardForm, PersonalCSVImportForm
from .models import Card, Expansion, Game, OwnedCard, ValueSnapshot
from .services import RANGES, build_chart_series, parse_range, refresh_snapshot


# Se loggato, mostra l'andamento della collezione con i range selezionabili.
def home(request):
    if not request.user.is_authenticated:
        games = Game.objects.exclude(logo='')[:4]
        return render(request, 'landing.html', {'games': games})

    # Garantisce che lo snapshot di oggi esista e rifletta le carte correnti
    refresh_snapshot(request.user)

    # Range selezionato: 1D, 7D, 14D, 1M, 3M, 6M, 1Y, 5Y, ALL
    range_key = parse_range(request.GET.get('range'))
    days = RANGES[range_key][1]

    snapshots = ValueSnapshot.objects.filter(owner=request.user)
    if days is not None:
        start = timezone.now().date() - timedelta(days=days)
        snapshots = snapshots.filter(date__gte=start)

    series = build_chart_series(list(snapshots), range_key)

    context = {
        'ranges': [
            {'key': key, 'label': label, 'active': key == range_key}
            for key, (label, _) in RANGES.items()
        ],
        'current_range': range_key,
    }
    context.update(series)
    return render(request, 'home.html', context)



# Riutilizzato dalle view che devono operare soltanto sulle carte del proprietario.
class OwnerRequiredMixin:
    # Filtra il queryset per mostrare solo gli oggetti dell'utente loggato (owner)
    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


# Collezione con paginazione + filtri (testo sul nome, gioco del catalogo),
# così la lista resta leggera anche con migliaia di carte.
class CollectionListView(LoginRequiredMixin, ListView):
    model = OwnedCard
    template_name = 'cards/collection_list.html'
    context_object_name = 'owned_cards'
    paginate_by = 24

    def get_queryset(self):
        # status='owned': esclude le carte vendute, che stanno in un'altra view
        qs = OwnedCard.objects.filter(
            owner=self.request.user, status='owned'
        ).select_related('card__expansion__game').order_by('-id')

        query = self.request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(card__name__icontains=query)

        game_id = self.request.GET.get('game', '').strip()
        if game_id.isdigit():
            qs = qs.filter(card__expansion__game_id=int(game_id))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Totali calcolati su TUTTI i risultati del filtro (non solo la pagina)
        full_qs = self.get_queryset()
        agg = full_qs.aggregate(count=Count('id'), total=Sum('market_value'))
        context['total_count'] = agg['count']
        context['total_value'] = agg['total'] or 0
        context['games'] = Game.objects.all().order_by('name')
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'game': self.request.GET.get('game', ''),
        }
        return context


# owner assegnato in form_valid, mai disponibile come campo del form, si è automaticamente proprietari della carta che si crea salvo cessione
class OwnedCardCreateView(LoginRequiredMixin, CreateView):
    model = OwnedCard
    form_class = OwnedCardForm
    template_name = 'cards/collection_form.html'
    success_url = reverse_lazy('collection')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Permette di pre-selezionare una carta via ?card=<pk> (es. dal catalogo)
        preselect = self.request.GET.get('card', '')
        context['preselect_card_id'] = preselect if preselect.isdigit() else ''
        return context

    def form_valid(self, form):
        form.instance.owner = self.request.user  # imposto automaticamente il valore per garantire il funzionamento
        response = super().form_valid(form)
        refresh_snapshot(self.request.user)  # il valore della collezione è cambiato
        return response


# Aggiorna copia fisica
class OwnedCardUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    # OwnerRequiredMixin filtra il queryset: non si può modificare una carta altrui, anche sapendo l'id nel url
    model = OwnedCard
    form_class = OwnedCardForm
    template_name = 'cards/collection_form.html'
    success_url = reverse_lazy('collection')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_card'] = self.object.card  # pre-carica la ricerca nel form
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        refresh_snapshot(self.request.user)
        return response


# Elimina dietro conferma
class OwnedCardDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    model = OwnedCard
    template_name = 'cards/collection_confirm_delete.html'
    success_url = reverse_lazy('collection')

    def form_valid(self, form):
        response = super().form_valid(form)
        refresh_snapshot(self.request.user)
        return response


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

            refresh_snapshot(request.user)
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
        return response


# Endpoint JSON per la ricerca nel catalogo (add/edit carta): sostituisce
# l'enorme <select> con migliaia di <option> -> ora si cerca e si sceglie.
class CardSearchView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        if not q:
            return JsonResponse({'results': []})

        cards = (
            Card.objects.filter(name__icontains=q)
            .select_related('expansion')
            .order_by('name', 'expansion__code', 'number')[:20]
        )

        results = []
        for c in cards:
            image = c.image_url or ''
            if not image and c.image:
                try:
                    image = c.image.url
                except ValueError:
                    image = ''
            results.append({
                'id': c.id,
                'name': c.name,
                'set_code': c.expansion.code,
                'set_name': c.expansion.name,
                'number': c.number,
                'rarity': c.rarity,
                'image_url': image,
                'display': f"{c.name} — {c.expansion.code} {c.number}",
            })
        return JsonResponse({'results': results})


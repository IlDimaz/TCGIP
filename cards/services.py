"""Business logic riutilizzabile: range del grafico, snapshot quotidiani,
calcolo delle serie relative e della variazione % nel periodo selezionato."""

from decimal import Decimal
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import ValueSnapshot, OwnedCard

# Chiave range -> (label visibile, giorni fino ad oggi). days=None significa "tutto".
RANGES = {
    '3D': ('3D', 3),
    '7D': ('7D', 7),
    '14D': ('14D', 14),
    '1M': ('1M', 30),
    '3M': ('3M', 90),
    '6M': ('6M', 180),
    '1Y': ('1Y', 365),
    '5Y': ('5Y', 1825),
    'ALL': ('ALL', None),
}


def parse_range(raw):
    """Ritorna una chiave valida di RANGES (default 'ALL')."""
    key = (raw or 'ALL').strip().upper()
    return key if key in RANGES else 'ALL'


def refresh_snapshot(owner):
    """Ricalcola il valore totale della collezione di oggi e aggiorna/crea
    lo snapshot di ValueSnapshot per la data odierna. Idempotente."""
    today = timezone.now().date()
    total = (
        OwnedCard.objects.filter(owner=owner, status='owned')
        .aggregate(total=Sum('market_value'))['total']
        or Decimal('0')
    )
    snapshot, created = ValueSnapshot.objects.get_or_create(
        owner=owner,
        date=today,
        defaults={'total_value': total},
    )
    if not created and snapshot.total_value != total:
        snapshot.total_value = total
        snapshot.save(update_fields=['total_value'])
    return snapshot


def build_chart_series(snapshots, range_key):
    """Trasforma una lista di ValueSnapshot in serie per Chart.js.

    - values: valori assoluti (€)
    - relative: valori "relativi", con il primo punto fissato a 100,
      così '3D' e 'ALL' diventano confrontabili a colpo d'occhio
    - change_pct: variazione % tra primo e ultimo punto del range
    - statica: un solo punto -> 0%, senza dati -> None
    """
    days = RANGES.get(range_key, ('ALL', None))[1]
    if days is not None:
        start = timezone.now().date() - timedelta(days=days)
        snapshots = [s for s in snapshots if s.date >= start]

    snapshots = sorted(snapshots, key=lambda s: s.date)
    labels = [s.date.strftime('%d/%m/%Y') for s in snapshots]
    values = [float(s.total_value) for s in snapshots]

    current = values[-1] if values else None
    first = values[0] if values else None

    if len(values) >= 2 and first:
        relative = [round(v / first * 100, 2) for v in values]
        change_abs = values[-1] - first
        change_pct = (change_abs / first) * 100
    elif values:
        relative = [100.0]
        change_abs = 0.0
        change_pct = 0.0
    else:
        relative = []
        change_abs = None
        change_pct = None

    return {
        'labels': labels,
        'values': values,
        'relative': relative,
        'current': current,
        'first': first,
        'change_abs': change_abs,
        'change_pct': change_pct,
    }

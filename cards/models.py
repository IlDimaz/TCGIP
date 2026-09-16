from django.db import models


# semplice creazione tcg di turno
class Game(models.Model):
    name = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='cards/games/', blank=True, null=True)

    def __str__(self):
        return self.name


# semplice creazione espansione di turno
class Expansion(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    release_date = models.DateField(null=True, blank=True)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='expansions')

    def __str__(self):
        return f"{self.name} ({self.code})"


class Card(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    expansion = models.ForeignKey(  # ogni carta ha 1 espansione, se cessa di esistere, la carta scompare di conseguenza
        Expansion,
        on_delete=models.CASCADE,
        related_name="cards"
    )
    number = models.CharField(max_length=20, db_index=True)
    rarity = models.CharField(max_length=50, blank=True, default='')
    # Immagini dal catalogo: image_url punta alla fonte remota (es. Scryfall),
    # image è una copia locale scaricata opzionalmente dal management command.
    image_url = models.URLField(max_length=500, blank=True)
    image = models.ImageField(upload_to='cards/catalog/', null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.expansion.code} {self.number}"

# Copia fisica posseduta da un utente; status/sale_price gestiscono la vendita (la carta deve essere catalogata da parte di Admin)
class OwnedCard(models.Model):
    STATUS_CHOICES = [
        ('owned', 'Posseduta'),
        ('sold', 'Venduta'),
    ]

    CARD_TYPE_CHOICES = [
        ('raw', 'Raw'),
        ('graded', 'Graded'),
    ]

    CONDITION_CHOICES = [
        ('NM', 'Near Mint'),
        ('LP', 'Lightly Played'),
        ('MP', 'Moderately Played'),
        ('HP', 'Heavily Played'),
        ('DMG', 'Damaged'),
    ]

    GRADING_COMPANY_CHOICES = [
        ('PSA', 'PSA'),
        ('BGS', 'Beckett (BGS)'),
        ('CGC', 'CGC'),
        ('SGC', 'SGC'),
    ]

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="copies")
    owner = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="cards")
    image = models.ImageField(upload_to="cards/owned/", null=True, blank=True)
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, default='raw')

    # Compilato solo se card_type == 'raw'
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, blank=True)

    # Compilati solo se card_type == 'graded'
    grading_company = models.CharField(max_length=10, choices=GRADING_COMPANY_CHOICES, blank=True)
    grade = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)

    # Tracking valore
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='owned')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    market_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sold_date = models.DateField(null=True, blank=True)

    language = models.CharField(max_length=30, default="Italiano")
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner', 'status']),
        ]

    def __str__(self):
        return f"{self.card.name} owned by {self.owner.username}"

    @property
    def display_image_url(self):
        """Immagine da mostrare in lista/dettaglio: foto scattata dall'utente,
        poi immagine del catalogo (locale/remota), altrimenti placeholder."""
        uploads = []
        if self.image:
            uploads.append(self.image)
        if self.card and self.card.image:
            uploads.append(self.card.image)
        for f in uploads:
            try:
                if f and getattr(f, 'name'):
                    return f.url
            except ValueError:
                continue
        if self.card and self.card.image_url:
            return self.card.image_url
        return None


# Gestione andamento collezione, valore salvato una volta per giorno per gestire il plotting del grafico relativo al valore nel tempo
class ValueSnapshot(models.Model):  # creazione tabella registrante prezzo e data, dati poi usati per il plotting
    owner = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="value_snapshots")
    date = models.DateField()
    total_value = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ['owner', 'date']  # 1 owner può avere al più 1 valore per data
        ordering = ['date']  # sort by date, comodo per plot

    def __str__(self):
        return f"{self.owner.username} - {self.date} - {self.total_value}€"  # print simil "Dima - 2026-08-20 - 1250.50€"
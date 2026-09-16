from django.contrib import admin
from .models import Expansion, Card, OwnedCard, Game

# Semplice gestione del catalogo da parte di admin, preferibilmente non usata
admin.site.register(Expansion)
admin.site.register(Card)
admin.site.register(OwnedCard)
admin.site.register(Game)
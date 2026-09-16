from django.contrib import admin
from django.utils.html import format_html

from .models import Card, Expansion, Game, OwnedCard, ValueSnapshot


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('name', 'logo_preview')
    search_fields = ('name',)

    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="max-height:40px;">', obj.logo.url)
        return '-'
    logo_preview.short_description = 'Logo'


@admin.register(Expansion)
class ExpansionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'game', 'release_date')
    list_filter = ('game',)
    search_fields = ('name', 'code')


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('name', 'expansion', 'number', 'rarity', 'image_preview')
    list_filter = ('expansion', 'rarity')
    search_fields = ('name', 'number', 'expansion__code')
    list_per_page = 50

    def image_preview(self, obj):
        url = obj.image_url or ''
        if not url and obj.image:
            try:
                url = obj.image.url
            except ValueError:
                url = ''
        if not url:
            return '-'
        return format_html('<img src="{}" style="max-height:60px;">', url)
    image_preview.short_description = 'Immagine'


@admin.register(OwnedCard)
class OwnedCardAdmin(admin.ModelAdmin):
    list_display = ('card', 'owner', 'status', 'card_type', 'market_value')
    list_filter = ('status', 'card_type')
    search_fields = ('card__name', 'owner__username')
    autocomplete_fields = ('card', 'owner')


admin.site.register(ValueSnapshot)

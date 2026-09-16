from django.contrib import admin
from .models import Listing, Offer, Transaction, Review

admin.site.register(Listing)
admin.site.register(Offer)
admin.site.register(Transaction)
admin.site.register(Review)
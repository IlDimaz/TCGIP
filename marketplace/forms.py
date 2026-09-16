from django import forms
from .models import Listing, Offer, Review
from cards.models import OwnedCard

class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = ['owned_card', 'price', 'listing_type', 'auction_end', 'shipping_available', 'pickup_available', 'description']
        widgets = {
            'owned_card': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'listing_type': forms.Select(attrs={'class': 'form-select'}),
            'auction_end': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'shipping_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pickup_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['owned_card'].queryset = OwnedCard.objects.filter( #si venmdono solo le carte possedute e che non sono già in vendita
                owner=user, status='owned'
            ).exclude(
                listings__is_active=True
            )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('listing_type') == 'auction' and not cleaned_data.get('auction_end'):
            raise forms.ValidationError('Le aste richiedono una data di fine.')
        return cleaned_data


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ['amount', 'message']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control mb-2'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Messaggio (opzionale)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['amount'].required = True


class MessageForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Scrivi un messaggio...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['message'].required = True


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        
class ListingEditForm(forms.ModelForm):
    image = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Listing
        fields = ['price', 'description']
        widgets = {
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def save(self, commit=True):
        listing = super().save(commit=commit)
        image = self.cleaned_data.get('image')
        if image:
            listing.owned_card.image = image
            listing.owned_card.save()
        return listing

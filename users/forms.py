from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

#gestione settings profilo
class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_image', 'city', 'province', 'country', 'allow_location', 'collection_public']
        widgets = {
            'allow_location': forms.CheckboxInput(),
            'collection_public': forms.CheckboxInput(),
        }
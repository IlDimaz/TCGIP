from django import forms
from .models import OwnedCard, Game, Expansion

# Import catalogo (admin): scegli espansione esistente O nuova, chiamata @staff_member_required in views
class CSVImportForm(forms.Form):
    csv_file = forms.FileField(label='File CSV')
    game = forms.ModelChoiceField(queryset=Game.objects.all(), label='Gioco')
    expansion = forms.ModelChoiceField(
        queryset=Expansion.objects.all(),
        label='Espansione esistente',
        required=False,
        help_text='Lascia vuoto se vuoi crearne una nuova'
    )
    new_expansion_name = forms.CharField(
        max_length=100,
        label='Nome nuova espansione',
        required=False
    )
    new_expansion_code = forms.CharField(
        max_length=20,
        label='Codice nuova espansione',
        required=False,
        help_text='Es. OP-03, MEW, LOR (obbligatorio se crei una nuova espansione)'
    )
# Clean valida il form vrificando che l'utente scelga una sola modalità per l'espansione tra le due seguenti:
# 1 selezionare un'espansione esistente 2 oppure inserirne una nuova. gestisce poi le eccezioni
    def clean(self):
        cleaned_data = super().clean()
        expansion = cleaned_data.get('expansion')
        new_expansion_name = cleaned_data.get('new_expansion_name')
        new_expansion_code = cleaned_data.get('new_expansion_code')

        if not expansion and not new_expansion_name:
            raise forms.ValidationError(
                'Devi selezionare un\'espansione esistente oppure inserire il nome di una nuova.'
            )
        if expansion and new_expansion_name:
            raise forms.ValidationError(
                'Scegli solo una opzione: espansione esistente OPPURE nuova espansione, non entrambe.'
            )
        if new_expansion_name:
            if not new_expansion_code:
                raise forms.ValidationError(
                    'Se crei una nuova espansione, devi specificare anche il suo codice univoco (es. OP-03).'
                )
            code = new_expansion_code.strip().upper()
            cleaned_data['new_expansion_code'] = code
            if Expansion.objects.filter(code=code).exists():
                raise forms.ValidationError(
                    f'Esiste già un\'espansione con il codice "{code}".'
                )
        return cleaned_data

# semplice form inserimento carte con parametri vari ed eventuali
class OwnedCardForm(forms.ModelForm):
    class Meta:
        model = OwnedCard
        fields = ['card', 'image', 'card_type', 'condition', 'grading_company', 'grade',
                  'language', 'notes', 'purchase_price', 'market_value', 'status']
        widgets = {
            # 'card' è nascosto: il template offre una ricerca che compila questo campo.
            # Niente più <select> con migliaia di <option> -> la pagina resta leggera.
            'card': forms.HiddenInput(attrs={'id': 'id_card'}),
            'card_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_card_type'}),
            'condition': forms.Select(attrs={'class': 'form-select', 'id': 'id_condition'}),
            'grading_company': forms.Select(attrs={'class': 'form-select', 'id': 'id_grading_company'}),
            'grade': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_grade', 'step': '0.5', 'min': '1', 'max': '10'}),
            'language': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'purchase_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'market_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        error_messages = {
            'card': {
                'required': 'Seleziona una carta dal catalogo usando la ricerca qui sopra.',
                'invalid_choice': 'La carta selezionata non è più disponibile nel catalogo.',
            },
        }

# Import collezione personale, attenzione, le carte devono già esistere nel catalogo  
class PersonalCSVImportForm(forms.Form):
    csv_file = forms.FileField(label='File CSV della tua collezione')
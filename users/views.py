from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DetailView, ListView
from django.contrib import messages
from marketplace.models import Review
from cards.models import OwnedCard 
from .forms import CustomUserCreationForm, ProfileForm
from .models import User

# Crea un account e rimanda alla pagina di accesso.

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

# Mostra il profilo con annunci e recensioni dell'utente corrente.
class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'users/profile_detail.html'
    context_object_name = 'profile_user'

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['listings'] = self.request.user.listings.filter(is_active=True)
        context['reviews'] = Review.objects.filter(transaction__seller=self.request.user)
        return context

# Aggiorna esclusivamente il profilo dell'utente autenticato.
class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = 'users/profile_form.html'
    success_url = reverse_lazy('profile')

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profilo aggiornato con successo.')
        return super().form_valid(form)
    
class PublicProfileView(DetailView):
    # Espone solo i dati che il proprietario ha scelto di rendere pubblici.
    model = User
    template_name = 'users/public_profile.html'
    context_object_name = 'profile_user'
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['listings'] = self.object.listings.filter(is_active=True)
        context['reviews'] = Review.objects.filter(transaction__seller=self.object)

        # Collezione visibile solo se pubblica O se sei tu stesso
        is_owner = self.request.user == self.object
        if self.object.collection_public or is_owner:
            context['collection'] = OwnedCard.objects.filter(
                owner=self.object, status='owned'
            ).select_related('card').prefetch_related('listings')
        else:
            context['collection'] = None
        context['is_owner'] = is_owner
        return context
    
# Ricerca utenti per username con un limite per non caricare troppi risultati a schermo.
class UserSearchView(ListView): 
    model = User
    template_name = 'users/user_search.html'
    context_object_name = 'results'

    def get_queryset(self):
        query = self.request.GET.get('q', '')
        if not query:
            return User.objects.none()
        return User.objects.filter(username__icontains=query)[:20]

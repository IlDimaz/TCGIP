from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('profile/', views.ProfileDetailView.as_view(), name='profile'),
    path('profile/edit/', views.ProfileUpdateView.as_view(), name='profile-edit'),
    path('u/<str:username>/', views.PublicProfileView.as_view(), name='public-profile'),
    path('search/', views.UserSearchView.as_view(), name='user-search'),
]
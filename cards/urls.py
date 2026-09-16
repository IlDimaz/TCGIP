from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('collection/', views.CollectionListView.as_view(), name='collection'),
    path('collection/add/', views.OwnedCardCreateView.as_view(), name='collection-add'),
    path('collection/edit/<int:pk>/', views.OwnedCardUpdateView.as_view(), name='collection-edit'),
    path('collection/delete/<int:pk>/', views.OwnedCardDeleteView.as_view(), name='collection-delete'),
    path('admin-tools/import-cards/', views.import_cards_view, name='import-cards'),
    path('collection/sold/', views.SoldCardsListView.as_view(), name='sold-cards'),
    path('collection/import/', views.ImportPersonalCollectionView.as_view(), name='import-personal-collection'),
    path('collection/export/', views.ExportCollectionView.as_view(), name='export-collection'),
    path('api/cards/search/', views.CardSearchView.as_view(), name='card-search'),
]
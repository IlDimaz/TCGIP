from django.urls import path
from . import views

urlpatterns = [
    path('', views.ListingListView.as_view(), name='marketplace-list'),
    path('create/', views.ListingCreateView.as_view(), name='marketplace-create'),
    path('<int:pk>/', views.ListingDetailView.as_view(), name='marketplace-detail'),
    path('<int:pk>/offer/', views.OfferCreateView.as_view(), name='offer-create'),
    path('offer/<int:pk>/accept/', views.OfferAcceptView.as_view(), name='offer-accept'),
    path('offer/<int:pk>/reject/', views.OfferRejectView.as_view(), name='offer-reject'),
    path('offer/<int:pk>/counter/', views.CounterOfferView.as_view(), name='offer-counter'),
    path('transaction/<int:pk>/complete/', views.TransactionCompleteView.as_view(), name='transaction-complete'),
    path('purchases/', views.MyPurchasesView.as_view(), name='my-purchases'),
    path('sales/', views.MySalesView.as_view(), name='my-sales'),
    path('transaction/<int:pk>/review/', views.ReviewCreateView.as_view(), name='review-create'),
    path('<int:pk>/bid/', views.BidCreateView.as_view(), name='bid-create'),
    path('<int:pk>/contact/', views.MessageCreateView.as_view(), name='message-create'),
    path('offer/<int:pk>/reply/', views.MessageReplyView.as_view(), name='message-reply'),
    path('<int:pk>/buy/', views.BuyNowView.as_view(), name='buy-now'),
    path('my-listings/', views.MyListingsView.as_view(), name='my-listings'),
    path('<int:pk>/edit/', views.ListingEditView.as_view(), name='listing-edit'),
]

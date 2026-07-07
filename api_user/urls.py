from django.urls import path
from .views import *

urlpatterns = [
   path('auth/register/', UserRegisterAPIView.as_view(), name='user_register'),
    path('auth/login/', UserLoginAPIView.as_view(), name='user_login'),
    path('auth/verify-otp/', VerifyOTPAPIView.as_view(), name='user_verify_otp'),
    path('order/place/', PlaceOrderAPIView.as_view(), name='place_order'),
    path('list/',          AnimalListView.as_view(), name='list'),
    path('animals/detail/', AnimalDetailView.as_view(),name='animal_detail'),
    path('slots/available-dates/', AvailableDatesAPIView.as_view(), name='available_dates'),
    path('slots/by-date/',         SlotsByDateAPIView.as_view(),    name='slots_by_date'),

]
from django.urls import path
from . import views

urlpatterns = [
   path('auth/register/', views.UserRegisterAPIView.as_view(), name='user_register'),
    path('auth/login/', views.UserLoginAPIView.as_view(), name='user_login'),
    path('auth/verify-otp/', views.VerifyOTPAPIView.as_view(), name='user_verify_otp'),
    path('order/place/', views.PlaceOrderAPIView.as_view(), name='place_order'),
]
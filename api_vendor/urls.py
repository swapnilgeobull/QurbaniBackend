from django.urls import path
from . import views

urlpatterns = [

    path('auth/register/', views.VendorRegisterAPIView.as_view(), name='vendor_register'),
    

    path('auth/login/', views.VendorLoginAPIView.as_view(), name='vendor_login'),
    

    path('auth/verify-otp/', views.VendorVerifyOTPAPIView.as_view(), name='vendor_verify_otp'),

    path('inventory/add/', views.AddAnimalAPIView.as_view(), name='add_animal'),
    path('profile/get/', views.GetVendorProfileAPIView.as_view(), name='get_vendor_profile'),
    path('profile/edit/', views.EditVendorProfileAPIView.as_view(), name='edit_vendor_profile'),
    path('inventory/list/', views.GetInventoryListAPIView.as_view(), name='get_inventory_list'),
]
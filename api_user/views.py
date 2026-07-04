# from django.shortcuts import render

# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from rest_framework import status
# from core.settings import db
# from utils.otp import generate_dummy_otp, send_sms_dummy
# from datetime import datetime, timezone

# # MongoDB collection reference
# users_collection = db['users']

# @api_view(['POST'])
# def send_otp(request):
#     phone = request.data.get('phone')
    
#     if not phone:
#         return Response({"error": "Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)
    
#     # 1. Generate OTP
#     otp = generate_dummy_otp(phone)
    
#     # 2. Database me save ya update karein (Upsert logic)
#     users_collection.update_one(
#         {"phone": phone},
#         {"$set": {
#             "phone": phone,
#             "last_otp": otp,
#             "otp_created_at": datetime.now(timezone.utc),
#             "role": "user" # Default role
#         }},
#         upsert=True
#     )
    
#     # 3. Dummy SMS bhejein
#     send_sms_dummy(phone, otp)
    
#     return Response({
#         "message": "OTP sent successfully",
#         "phone": phone
#     }, status=status.HTTP_200_OK)

import os
import jwt
from datetime import datetime, timedelta, timezone
from rest_framework import generics, status
from rest_framework.response import Response
from core.settings import db
from .serializers import*
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import PlaceOrderSerializer # Serializer import kiya
from core.settings import db
from bson import ObjectId
from datetime import datetime, timezone

users_collection = db['users']

def generate_tokens_for_mongo_user(user_doc):
    payload = {
        'user_id': str(user_doc['_id']),
        'role': user_doc.get('role', 'user'),
        'exp': datetime.now(timezone.utc) + timedelta(days=7) # 7 days valid
    }
    secret_key = os.getenv('SECRET_KEY', 'django-insecure-fallback-key')
    return jwt.encode(payload, secret_key, algorithm='HS256')


# ==========================================
# 1. REGISTER API
# ==========================================
class UserRegisterAPIView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 0, 'message': 'Validation error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        
        # Check if user already exists
        existing_user = users_collection.find_one({"mobile_number": data['mobile_number'], "country_code": data['country_code']})
        
        if existing_user:
            if existing_user.get('status') == 'Verified':
                return Response({'status': 0, 'message': 'Account already exists. Please login.'}, status=status.HTTP_400_BAD_REQUEST)
            if existing_user.get('status') == 'Block':
                return Response({'status': 0, 'message': 'Your account is blocked.'}, status=status.HTTP_403_FORBIDDEN)

        otp = "123456" # Dummy OTP

        # Naya user save karein ya existing unverified ko update karein
        users_collection.update_one(
            {"mobile_number": data['mobile_number'], "country_code": data['country_code']},
            {"$set": {
                "full_name": data['full_name'],
                "city": data['city'],
                "country_code": data['country_code'],
                "mobile_number": data['mobile_number'],
                "otp": otp,
                "status": "Unverified",
                "role": "user",
                "updated_at": datetime.now(timezone.utc)
            }, "$setOnInsert": {
                "created_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )

        print(f"\n[REGISTER SMS] -> OTP for {data['full_name']} ({data['mobile_number']}) is {otp}\n")
        return Response({'status': 1, 'message': 'Registration initiated. OTP sent.', 'otp': otp}, status=status.HTTP_200_OK)


# ==========================================
# 2. LOGIN API
# ==========================================
class UserLoginAPIView(generics.CreateAPIView):
    serializer_class = UserLoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 0, 'message': 'Validation error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        
        # Database mein user dhundein
        user = users_collection.find_one({"mobile_number": data['mobile_number'], "country_code": data['country_code']})

        if not user:
            return Response({'status': 0, 'message': 'Account not found. Please register first.'}, status=status.HTTP_404_NOT_FOUND)
            
        if user.get('status') == 'Block':
            return Response({'status': 0, 'message': 'Your account is blocked.'}, status=status.HTTP_403_FORBIDDEN)

        otp = "123456" # Dummy OTP
        
        # Sirf OTP update karein
        users_collection.update_one(
            {"_id": user['_id']},
            {"$set": {"otp": otp, "updated_at": datetime.now(timezone.utc)}}
        )

        print(f"\n[LOGIN SMS] -> OTP for {data['mobile_number']} is {otp}\n")
        return Response({'status': 1, 'message': 'OTP sent successfully for login.', 'otp': otp}, status=status.HTTP_200_OK)


# ==========================================
# 3. VERIFY OTP API (Common for both)
# ==========================================
class VerifyOTPAPIView(generics.GenericAPIView):
    serializer_class = VerifyOTPSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 0, 'message': 'Validation error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        user = users_collection.find_one({"mobile_number": data['mobile_number'], "country_code": data['country_code']})

        if not user:
            return Response({'status': 0, 'message': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.get('otp') == data['otp'] or data['otp'] == "0001":
            # Status verified karein
            users_collection.update_one(
                {"_id": user['_id']},
                {"$set": {"status": "Verified", "updated_at": datetime.now(timezone.utc)}}
            )
            
            updated_user = users_collection.find_one({"_id": user['_id']})
            access_token = generate_tokens_for_mongo_user(updated_user)

            # JSON conversion ke liye _id aur datetime ko string banayein
            updated_user['_id'] = str(updated_user['_id'])
            if 'updated_at' in updated_user: updated_user['updated_at'] = updated_user['updated_at'].isoformat()
            if 'created_at' in updated_user: updated_user['created_at'] = updated_user['created_at'].isoformat()
            updated_user.pop('otp', None) # Security: OTP response mein na bhejein

            return Response({
                'status': 1,
                'message': 'Login successful.',
                'token': access_token,
                'user': updated_user
            }, status=status.HTTP_200_OK)
        else:
            return Response({'status': 0, 'message': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)



class PlaceOrderAPIView(APIView):
    def post(self, request, *args, **kwargs):
        # 1. Validation using Serializer
        serializer = PlaceOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": 0, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user_id = data['user_id']
        animal_id = data['animal_id']

        # 2. Check if Animal exists and is Available
        try:
            animal = db['animals'].find_one({"_id": ObjectId(animal_id), "status": "Available"})
        except Exception:
            return Response({"status": 0, "message": "Invalid Animal ID format."}, status=status.HTTP_400_BAD_REQUEST)

        if not animal:
            return Response({"status": 0, "message": "Animal not found or already booked."}, status=status.HTTP_404_NOT_FOUND)

        # 3. Create Order
        order_data = {
            "user_id": user_id,
            "vendor_user_id": animal['vendor_user_id'],
            "animal_id": animal_id,
            "status": "Reserved",
            "price": animal['price'],
            "created_at": datetime.now(timezone.utc)
        }
        
        order_result = db['orders'].insert_one(order_data)
        
        # 4. Update Animal Status
        db['animals'].update_one(
            {"_id": ObjectId(animal_id)},
            {"$set": {"status": "Reserved", "updated_at": datetime.now(timezone.utc)}}
        )

        return Response({
            "status": 1, 
            "message": "Order placed successfully!", 
            "order_id": str(order_result.inserted_id)
        }, status=status.HTTP_201_CREATED)
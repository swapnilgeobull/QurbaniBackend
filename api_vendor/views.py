import os
import jwt
from datetime import datetime, timedelta, timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.files.storage import FileSystemStorage
from pymongo import ReturnDocument
from core.settings import db
from bson.objectid import ObjectId
from pymongo import ReturnDocument, ASCENDING
from .serializers import*

users_collection = db['users']
vendors_collection = db['vendors']

def generate_tokens_for_mongo_user(user_doc):
    payload = {
        'user_id': str(user_doc['_id']),
        'role': user_doc.get('role', 'vendor'),
        'exp': datetime.now(timezone.utc) + timedelta(days=30)
    }
    secret_key = os.getenv('SECRET_KEY', 'django-insecure-fallback-key')
    return jwt.encode(payload, secret_key, algorithm='HS256')


def get_token_data(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, None
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(
            token,
            os.getenv('SECRET_KEY', 'django-insecure-fallback-key'),
            algorithms=['HS256']
        )
        return payload.get('user_id'), payload.get('role')
    except Exception:
        return None, None

# ==========================================
# 1. VENDOR REGISTER API
# ==========================================
class VendorRegisterAPIView(generics.CreateAPIView):
    serializer_class = VendorRegistrationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 0, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        
        # Check existing user
        existing_user = users_collection.find_one({"mobile_number": data['mobile_number'], "country_code": data['country_code']})
        if existing_user:
            if existing_user.get('role') != 'vendor':
                return Response({'status': 0, 'message': 'This number is registered as a customer.'}, status=status.HTTP_403_FORBIDDEN)
            if existing_user.get('status') == 'Verified':
                return Response({'status': 0, 'message': 'Vendor already exists. Please login.'}, status=status.HTTP_400_BAD_REQUEST)

        otp = "123456"

        # Update or Insert in users collection
        user_doc = users_collection.find_one_and_update(
            {"mobile_number": data['mobile_number'], "country_code": data['country_code']},
            {"$set": {
                "full_name": data['full_name'],
                "otp": otp,
                "status": "Unverified",
                "role": "vendor",
                "updated_at": datetime.now(timezone.utc)
            }, "$setOnInsert": {
                "created_at": datetime.now(timezone.utc)
            }},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

        # Update or Insert in vendors collection
        vendors_collection.update_one(
            {"user_id": str(user_doc['_id'])},
            {"$set": {
                "slaughterhouse_name": data['slaughterhouse_name'],
                "city": data['city'],
                "capacity": data['capacity'],
                "rating": 0.0,
                "updated_at": datetime.now(timezone.utc)
            }, "$setOnInsert": {
                "created_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )

        print(f"\n[VENDOR REGISTER SMS] -> OTP for {data['slaughterhouse_name']} is {otp}\n")
        return Response({'status': 1, 'message': 'Vendor registration initiated. OTP sent.', 'otp': otp}, status=status.HTTP_200_OK)

# ==========================================
# 2. VENDOR LOGIN API
# ==========================================
class VendorLoginAPIView(generics.CreateAPIView):
    serializer_class = VendorLoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 0, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = users_collection.find_one({"mobile_number": data['mobile_number'], "country_code": data['country_code']})

        if not user:
            return Response({'status': 0, 'message': 'Vendor account not found. Please register.'}, status=status.HTTP_404_NOT_FOUND)
            
        if user.get('role') != 'vendor':
            return Response({'status': 0, 'message': 'Unauthorized Access. You are not a vendor.'}, status=status.HTTP_403_FORBIDDEN)

        otp = "123456"
        users_collection.update_one({"_id": user['_id']}, {"$set": {"otp": otp, "updated_at": datetime.now(timezone.utc)}})

        print(f"\n[VENDOR LOGIN SMS] -> OTP for {data['mobile_number']} is {otp}\n")
        return Response({'status': 1, 'message': 'OTP sent successfully.', 'otp': otp}, status=status.HTTP_200_OK)

# ==========================================
# 3. VENDOR VERIFY OTP API
# ==========================================
class VendorVerifyOTPAPIView(generics.GenericAPIView):
    serializer_class = VendorVerifyOTPSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 0, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = users_collection.find_one({"mobile_number": data['mobile_number'], "country_code": data['country_code']})

        if not user or user.get('role') != 'vendor':
            return Response({'status': 0, 'message': 'Vendor profile not found or unauthorized.'}, status=status.HTTP_404_NOT_FOUND)

        if user.get('otp') == data['otp'] or data['otp'] == "0001":
            users_collection.update_one({"_id": user['_id']}, {"$set": {"status": "Verified", "updated_at": datetime.now(timezone.utc)}})
            
            updated_user = users_collection.find_one({"_id": user['_id']})
            vendor_details = vendors_collection.find_one({"user_id": str(user['_id'])})
            
            access_token = generate_tokens_for_mongo_user(updated_user)

            # Formatting response data
            updated_user['_id'] = str(updated_user['_id'])
            updated_user.pop('otp', None)
            if 'updated_at' in updated_user: updated_user['updated_at'] = updated_user['updated_at'].isoformat()
            if 'created_at' in updated_user: updated_user['created_at'] = updated_user['created_at'].isoformat()
            
            if vendor_details:
                vendor_details['_id'] = str(vendor_details['_id'])
                updated_user['business_details'] = vendor_details

            return Response({
                'status': 1,
                'message': 'Vendor Login successful.',
                'token': access_token,
                'user': updated_user
            }, status=status.HTTP_200_OK)
        else:
            return Response({'status': 0, 'message': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)



# ==========================================
# 4. VENDOR ADD ANIMAL (INVENTORY) API
# ==========================================
class AddAnimalAPIView(generics.CreateAPIView):
    serializer_class = AddAnimalSerializer

    def post(self, request, *args, **kwargs):
        # 1. Token Verification (Gatekeeper)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({'status': 0, 'message': 'Authorization token is missing or invalid.'}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header.split(' ')[1]
        try:
            secret_key = os.getenv('SECRET_KEY', 'django-insecure-fallback-key')
            decoded_token = jwt.decode(token, secret_key, algorithms=['HS256'])
            token_user_id = decoded_token.get('user_id')
            role = decoded_token.get('role')

            if role != 'vendor':
                return Response({'status': 0, 'message': 'Only authorized vendors can add inventory.'}, status=status.HTTP_403_FORBIDDEN)

        except Exception:
            return Response({'status': 0, 'message': 'Invalid or expired token.'}, status=status.HTTP_401_UNAUTHORIZED)

        # 2. Data Validation
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 0, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        body_user_id = str(data['user_id']).strip()

        # Security Check
        if body_user_id != token_user_id:
            return Response({'status': 0, 'message': 'Security Alert: You cannot add inventory for another vendor.'}, status=status.HTTP_403_FORBIDDEN)

        # Fetch Vendor Details
        vendor_doc = vendors_collection.find_one({"user_id": body_user_id})
        if not vendor_doc:
            return Response({'status': 0, 'message': 'Vendor business profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        images_list = request.FILES.getlist('images') # Frontend se aayi saari images pakdo
        image_urls = []
        fs = FileSystemStorage()
        
        for image in images_list:
            # Image ko save karna aur uska unique naam banana
            filename = fs.save(image.name, image)
            uploaded_file_url = fs.url(filename)
            # URL ko hamari list mein add karna (e.g., /media/goat_pic.jpg)
            image_urls.append(uploaded_file_url)

        # 4. Prepare & Insert Data into PyMongo
        animal_data = {
            "vendor_id": str(vendor_doc['_id']),
            "vendor_user_id": body_user_id,
            "slaughterhouse_name": vendor_doc.get('slaughterhouse_name'),
            "city": vendor_doc.get('city'),
            "animal_category": data['animal_category'],
            "breed": data['breed'],
            "age": data['age'],
            "weight": data['weight'],
            "price": data['price'],
            "images": image_urls, # Yahan naye image URLs jayenge
            "description": data.get('description', ''),
            "status": "Available",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        # MongoDB Insert
        result = db['animals'].insert_one(animal_data)
        animal_data['_id'] = str(result.inserted_id)

        return Response({'status': 1, 'message': 'Animal with images added successfully.', 'data': animal_data}, status=status.HTTP_201_CREATED)

users_collection = db['users']
vendors_collection = db['vendors']

# ==========================================
# 5. GET VENDOR PROFILE API (POST Method via Body ID)
# ==========================================
class GetVendorProfileAPIView(APIView):
    def post(self, request, *args, **kwargs):
        # Seedha request body se user_id nikalna
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({"status": 0, "error": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # PyMongo query with ObjectId conversion
            user_doc = users_collection.find_one({"_id": ObjectId(user_id)})
            vendor_doc = vendors_collection.find_one({"user_id": str(user_id)})
        except Exception:
            return Response({"status": 0, "message": "Invalid User ID format."}, status=status.HTTP_400_BAD_REQUEST)

        if not user_doc or not vendor_doc:
            return Response({'status': 0, 'message': 'Vendor profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Response structure matching your exact requirements
        profile_data = {
            "user_id": str(user_doc['_id']),
            "full_name": user_doc.get('full_name'),
            "mobile_number": user_doc.get('mobile_number'),
            "slaughterhouse_name": vendor_doc.get('slaughterhouse_name'),
            "city": vendor_doc.get('city'),
            "capacity": vendor_doc.get('capacity'),
            "rating": vendor_doc.get('rating')
        }

        return Response({
            'status': 1, 
            'msg': 'data', 
            'data': profile_data
        }, status=status.HTTP_200_OK)


# ==========================================
# 6. EDIT VENDOR PROFILE API (POST Method via Body ID)
# ==========================================
class EditVendorProfileAPIView(generics.GenericAPIView):
    serializer_class = VendorProfileUpdateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
            user_id = serializer.validated_data.get('user_id')
            
            # Check if user exists in MongoDB
            user_doc = users_collection.find_one({"_id": ObjectId(user_id)})
            vendor_doc = vendors_collection.find_one({"user_id": str(user_id)})
        except Exception:
            return Response({
                'status': 0,
                'message': 'User not found or invalid ID format.'
            }, status=status.HTTP_404_NOT_FOUND)

        if not user_doc or not vendor_doc:
            return Response({
                'status': 0,
                'message': 'Vendor profile not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        data = serializer.validated_data
        user_updates = {}
        vendor_updates = {}

        # Fields filter and assignment block (just like your reference logic)
        if 'full_name' in data: 
            user_updates['full_name'] = data.get('full_name')
            
        if 'slaughterhouse_name' in data: 
            vendor_updates['slaughterhouse_name'] = data.get('slaughterhouse_name')
        if 'city' in data: 
            vendor_updates['city'] = data.get('city')
        if 'capacity' in data: 
            vendor_updates['capacity'] = data.get('capacity')

        # Execution of Updates via PyMongo
        if user_updates:
            user_updates['updated_at'] = datetime.now(timezone.utc)
            users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": user_updates})

        if vendor_updates:
            vendor_updates['updated_at'] = datetime.now(timezone.utc)
            vendors_collection.update_one({"user_id": str(user_id)}, {"$set": vendor_updates})

        return Response({
            'status': 1,
            'message': 'Profile updated successfully.'
        }, status=status.HTTP_200_OK)


# ==========================================
# 7. GET INVENTORY LIST API (POST Method)
# ==========================================
class GetInventoryListAPIView(APIView):
    def post(self, request, *args, **kwargs):
        # 1. Input Data
        user_id = request.data.get('user_id')
        role = request.data.get('role')

        # 2. Security & Role Validation
        if role != 'vendor':
            return Response({"status": 0, "message": "Access Denied: Only vendors can access inventory."}, status=status.HTTP_403_FORBIDDEN)
        
        if not user_id:
            return Response({"status": 0, "message": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # 3. MongoDB Query
        try:
            animals_cursor = db['animals'].find({"vendor_user_id": str(user_id)}).sort("created_at", -1)
            
            # 4. Data Conversion
            animals_list = []
            for animal in animals_cursor:
                animal['_id'] = str(animal.get('_id', ''))
                animal['images'] = animal.get('images', []) 
                
                if 'created_at' not in animal:
                    from datetime import datetime
                    animal['created_at'] = datetime.utcnow()
                
                animals_list.append(animal)

            # 5. Serialization
            serializer = InventoryListSerializer(animals_list, many=True)

            return Response({
                "status": 1, 
                "message": "Inventory fetched successfully.", 
                "count": len(serializer.data),
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"status": 0, "message": f"Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


slots_collection   = db['slots']
vendors_collection = db['vendors']

# ══════════════════════════════════════════
# 1. SLOT CREATE
#    POST /api/vendor/slots/create/
# ══════════════════════════════════════════
class SlotCreateAPIView(APIView):

    def post(self, request):
        # ── Auth ──
        user_id, role = get_token_data(request)
        if not user_id:
            return Response({
                'status':  0,
                'message': 'Authorization token missing or invalid.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        if role != 'vendor':
            return Response({
                'status':  0,
                'message': 'Only vendors can create slots.'
            }, status=status.HTTP_403_FORBIDDEN)

        # ── Validation ──
        serializer = SlotCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status':  0,
                'message': 'Validation error',
                'errors':  serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # ── Same slot already exist check ──
        existing = slots_collection.find_one({
            'vendor_user_id': user_id,
            'date':           str(data['date']),
            'time_from':      data['time_from'],
            'time_to':        data['time_to'],
        })
        if existing:
            return Response({
                'status':  0,
                'message': 'This slot already exists.'
            }, status=status.HTTP_400_BAD_REQUEST)

        now      = datetime.now(timezone.utc)
        slot_doc = {
            'vendor_user_id': user_id,
            'date':           str(data['date']),   # "2026-06-20"
            'time_from':      data['time_from'],   # "08:00 AM"
            'time_to':        data['time_to'],     # "09:00 AM"
            'capacity':       data['capacity'],
            'booked':         0,
            'created_at':     now,
            'updated_at':     now,
        }

        result = slots_collection.insert_one(slot_doc)
        slot_doc['_id']        = str(result.inserted_id)
        slot_doc['created_at'] = now.isoformat()
        slot_doc['updated_at'] = now.isoformat()

        return Response({
            'status':  1,
            'message': 'Slot created successfully.',
            'data':    slot_doc
        }, status=status.HTTP_201_CREATED)


# ══════════════════════════════════════════
# 2. SLOT LIST — Vendor ke saare slots
#    POST /api/vendor/slots/list/
# ══════════════════════════════════════════
class SlotListAPIView(APIView):
    def post(self, request):
        # ── Auth ──
        user_id, role = get_token_data(request)
        if not user_id:
            return Response({
                'status':  0,
                'message': 'Authorization token missing or invalid.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        if role != 'vendor':
            return Response({
                'status':  0,
                'message': 'Only vendors can view their slots.'
            }, status=status.HTTP_403_FORBIDDEN)

        # ── Optional date filter ──
        date = request.data.get('date')

        match_query = {'vendor_user_id': user_id}
        if date:
            match_query['date'] = date

        # ── Aggregation Pipeline ──
        # Fast — index on vendor_user_id + date
        pipeline = [
            {'$match': match_query},
            {'$sort':  {'date': ASCENDING, 'time_from': ASCENDING}},
            {'$project': {
                '_id':            {'$toString': '$_id'},
                'date':           1,
                'time_from':      1,
                'time_to':        1,
                'capacity':       1,
                'booked':         1,
                'remaining':      {'$subtract': ['$capacity', '$booked']},
                # Label automatically calculate
                'label': {
                    '$switch': {
                        'branches': [
                            # Full
                            {
                                'case':  {'$gte': ['$booked', '$capacity']},
                                'then':  'Full'
                            },
                            # Limited — 20% se kam bachi
                            {
                                'case': {
                                    '$lte': [
                                        {'$subtract': ['$capacity', '$booked']},
                                        {'$multiply': ['$capacity', 0.2]}
                                    ]
                                },
                                'then': 'Limited'
                            },
                        ],
                        'default': 'Good Time'
                    }
                },
                'created_at': {'$dateToString': {
                    'format': '%Y-%m-%dT%H:%M:%S',
                    'date':   '$created_at'
                }},
            }}
        ]

        slots = list(slots_collection.aggregate(pipeline))

        return Response({
            'status':  1,
            'message': 'Slots fetched successfully.',
            'count':   len(slots),
            'data':    slots
        }, status=status.HTTP_200_OK)


# ══════════════════════════════════════════
# 3. SLOT DELETE
#    POST /api/vendor/slots/delete/
# ══════════════════════════════════════════
class SlotDeleteAPIView(APIView):
    def post(self, request):
        # ── Auth ──
        user_id, role = get_token_data(request)
        if not user_id:
            return Response({
                'status':  0,
                'message': 'Authorization token missing or invalid.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        if role != 'vendor':
            return Response({
                'status':  0,
                'message': 'Only vendors can delete slots.'
            }, status=status.HTTP_403_FORBIDDEN)

        # ── Validation ──
        serializer = SlotDeleteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status':  0,
                'message': 'Validation error',
                'errors':  serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        slot_id = serializer.validated_data['slot_id']

        # ── Slot fetch ──
        try:
            slot = slots_collection.find_one({
                '_id':            ObjectId(slot_id),
                'vendor_user_id': user_id        # sirf apna slot delete kare
            })
        except Exception:
            return Response({
                'status':  0,
                'message': 'Invalid slot_id.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not slot:
            return Response({
                'status':  0,
                'message': 'Slot not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # ── Booked slot delete nahi hoga ──
        if slot.get('booked', 0) > 0:
            return Response({
                'status':  0,
                'message': f"Cannot delete. {slot['booked']} bookings already exist."
            }, status=status.HTTP_400_BAD_REQUEST)

        slots_collection.delete_one({'_id': ObjectId(slot_id)})

        return Response({
            'status':  1,
            'message': 'Slot deleted successfully.'
        }, status=status.HTTP_200_OK)
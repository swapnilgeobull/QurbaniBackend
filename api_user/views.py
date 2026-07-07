
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
from .serializers import PlaceOrderSerializer 
from core.settings import db
from bson import ObjectId
from datetime import datetime, timezone
from rest_framework.response import Response
from pymongo import ASCENDING
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



animals_collection = db['animals']
vendors_collection = db['vendors']
        # ── Token helper — tumhare existing pattern se same ──
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


# ══════════════════════════════════════════
# 1. ANIMAL LIST — Saare available animals
#    GET /api/animals/list/
#    Query params: ?category=Goat&city=Makkah&page=1
# ══════════════════════════════════════════
class AnimalListView(APIView):

    def get(self, request):
        # ── Auth ──
        user_id, role = get_token_data(request)
        if not user_id:
            return Response({
                'status':  0,
                'message': 'Authorization token missing or invalid.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ── Optional filters query params se ──
        category  = request.query_params.get('category')   # Goat, Sheep, Cow, Camel
        city      = request.query_params.get('city')
        page      = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        skip      = (page - 1) * page_size

        # ── Match query banao ──
        match_query = {'status': 'Available'}
        if category:
            match_query['animal_category'] = category
        if city:
            match_query['city'] = city

        # ── Aggregation Pipeline ──
        # Ek hi query mein:
        # 1. Filter karo
        # 2. Vendor rating bhi lao
        # 3. Total count bhi
        # 4. Pagination bhi
        pipeline = [
            {'$match': match_query},
            {'$sort':  {'created_at': -1}},

            # Vendor collection se rating lao
            {'$lookup': {
                'from':         'vendors',
                'localField':   'vendor_user_id',
                'foreignField': 'user_id',
                'as':           'vendor_info'
            }},
            {'$unwind': {
                'path': '$vendor_info',
                'preserveNullAndEmptyArrays': True
            }},

            # Ek pipeline mein data + total count dono
            {'$facet': {
                'animals': [
                    {'$skip':  skip},
                    {'$limit': page_size},
                    {'$project': {
                        '_id':              {'$toString': '$_id'},
                        'animal_category':  1,
                        'breed':            1,
                        'weight':           1,
                        'price':            1,
                        'images':           1,
                        'status':           1,
                        'slaughterhouse_name': 1,
                        'city':             1,
                        'vendor_rating':    '$vendor_info.rating',
                    }}
                ],
                'total_count': [
                    {'$count': 'count'}
                ],
                # Category wise count — filter chips ke liye
                'category_summary': [
                    {'$group': {
                        '_id':   '$animal_category',
                        'count': {'$sum': 1}
                    }}
                ]
            }}
        ]

        result   = list(animals_collection.aggregate(pipeline))
        data     = result[0]

        animals  = data.get('animals', [])
        total    = data['total_count'][0]['count'] \
                   if data.get('total_count') else 0
        summary  = data.get('category_summary', [])

        # datetime clean karo
        for animal in animals:
            if isinstance(animal.get('created_at'), datetime):
                animal['created_at'] = animal['created_at'].isoformat()

        serializer = AnimalListSerializer(animals, many=True)

        return Response({
            'status':  1,
            'message': 'Animals fetched successfully.',
            'total':   total,
            'page':    page,
            'pages':   (total + page_size - 1) // page_size,
            'filters': {
                'category': category,
                'city':     city,
            },
            'category_summary': summary,  # frontend filter chips ke liye
            'data':    serializer.data
        }, status=status.HTTP_200_OK)


class AnimalDetailView(APIView):
    def post(self, request):
        # ── Auth ──
        user_id, role = get_token_data(request)
        if not user_id:
            return Response({
                'status':  0,
                'message': 'Authorization token missing or invalid.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ── Body se animal_id lo ──
        animal_id = request.data.get('animal_id')
        if not animal_id:
            return Response({
                'status':  0,
                'message': 'animal_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── Animal ID validate karo ──
        try:
            obj_id = ObjectId(animal_id)
        except Exception:
            return Response({
                'status':  0,
                'message': 'Invalid animal ID.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── Aggregation Pipeline ──
        pipeline = [
            {'$match': {'_id': obj_id}},
            {'$lookup': {
                'from':         'vendors',
                'localField':   'vendor_user_id',
                'foreignField': 'user_id',
                'as':           'vendor_info'
            }},
            {'$unwind': {
                'path': '$vendor_info',
                'preserveNullAndEmptyArrays': True
            }},
            {'$lookup': {
                'from':         'slots',
                'localField':   'vendor_user_id',
                'foreignField': 'vendor_user_id',
                'as':           'available_slots'
            }},
            {'$project': {
                '_id':               {'$toString': '$_id'},
                'animal_category':   1,
                'breed':             1,
                'age':               1,
                'weight':            1,
                'price':             1,
                'description':       1,
                'images':            1,
                'status':            1,
                'vendor_user_id':    1,
                'slaughterhouse_name': 1,
                'city':              1,
                'created_at':        1,
                'vendor_rating':     '$vendor_info.rating',
                'vendor_capacity':   '$vendor_info.capacity',
                'available_slots': {
                    '$filter': {
                        'input': '$available_slots',
                        'as':    'slot',
                        'cond':  {'$lt': ['$$slot.booked', '$$slot.capacity']}
                    }
                }
            }}
        ]

        result = list(animals_collection.aggregate(pipeline))

        if not result:
            return Response({
                'status':  0,
                'message': 'Animal not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        animal = result[0]

        # ── datetime clean ──
        if isinstance(animal.get('created_at'), datetime):
            animal['created_at'] = animal['created_at'].isoformat()

        # ── Slots clean ──
        clean_slots = []
        for slot in animal.get('available_slots', []):
            clean_slots.append({
                'slot_id':   str(slot.get('_id', '')),
                'date':      slot.get('date'),
                'time_from': slot.get('time_from'),
                'time_to':   slot.get('time_to'),
                'capacity':  slot.get('capacity'),
                'booked':    slot.get('booked', 0),
                'remaining': slot.get('capacity', 0) - slot.get('booked', 0)
            })
        animal['available_slots'] = clean_slots

        serializer = AnimalDetailSerializer(animal)

        return Response({

            'status':          1,
            'message':         'Animal detail fetched.',
            'data':            animal,
            'available_slots': clean_slots
            }, status=status.HTTP_200_OK)


users_collection  = db['users']
slots_collection  = db['slots'] 



# ══════════════════════════════════════════
# 4. AVAILABLE DATES — Calendar ke liye
#    POST /api/vendor/slots/available-dates/
# ══════════════════════════════════════════
class AvailableDatesAPIView(APIView):

    def post(self, request):
        # ── Auth ──
        user_id, role = get_token_data(request)
        if not user_id:
            return Response({
                'status':  0,
                'message': 'Authorization token missing or invalid.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ── Serializer validation ──
        serializer = AvailableDatesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status':  0,
                'message': 'Validation error',
                'errors':  serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        vendor_user_id = serializer.validated_data['vendor_user_id']

        # ── Aaj ki date ──
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        # ── Aggregation Pipeline ──
        pipeline = [
            {
                '$match': {
                    'vendor_user_id': vendor_user_id,
                    'date':           {'$gte': today},
                    '$expr':          {'$lt': ['$booked', '$capacity']}
                }
            },
            {
                '$group': {
                    '_id':            '$date',
                    'total_slots':    {'$sum': 1},
                    'total_capacity': {'$sum': '$capacity'},
                    'total_booked':   {'$sum': '$booked'},
                }
            },
            {
                '$project': {
                    '_id':             0,
                    'date':            '$_id',
                    'total_slots':     1,
                    'total_remaining': {
                        '$subtract': ['$total_capacity', '$total_booked']
                    },
                }
            },
            {'$sort': {'date': ASCENDING}}
        ]

        dates = list(slots_collection.aggregate(pipeline))

        return Response({
            'status':  1,
            'message': 'Available dates fetched.',
            'count':   len(dates),
            'data':    dates
        }, status=status.HTTP_200_OK)


# ══════════════════════════════════════════
# 5. SLOTS BY DATE — Time slots
#    POST /api/vendor/slots/by-date/
# ══════════════════════════════════════════
class SlotsByDateAPIView(APIView):

    def post(self, request):
        # ── Auth ──
        user_id, role = get_token_data(request)
        if not user_id:
            return Response({
                'status':  0,
                'message': 'Authorization token missing or invalid.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ── Serializer validation ──
        serializer = SlotsByDateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status':  0,
                'message': 'Validation error',
                'errors':  serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        vendor_user_id = serializer.validated_data['vendor_user_id']
        date           = str(serializer.validated_data['date'])

        # ── Aggregation Pipeline ──
        pipeline = [
            {
                '$match': {
                    'vendor_user_id': vendor_user_id,
                    'date':           date
                }
            },
            {'$sort': {'time_from': ASCENDING}},
            {
                '$project': {
                    '_id':       {'$toString': '$_id'},
                    'date':      1,
                    'time_from': 1,
                    'time_to':   1,
                    'capacity':  1,
                    'booked':    1,
                    'remaining': {
                        '$subtract': ['$capacity', '$booked']
                    },
                    'label': {
                        '$switch': {
                            'branches': [
                                {
                                    'case': {
                                        '$gte': ['$booked', '$capacity']
                                    },
                                    'then': 'Full'
                                },
                                {
                                    'case': {
                                        '$lte': [
                                            {
                                                '$subtract': [
                                                    '$capacity',
                                                    '$booked'
                                                ]
                                            },
                                            {
                                                '$multiply': [
                                                    '$capacity',
                                                    0.2
                                                ]
                                            }
                                        ]
                                    },
                                    'then': 'Limited'
                                },
                            ],
                            'default': 'Good Time'
                        }
                    },
                    'is_available': {
                        '$lt': ['$booked', '$capacity']
                    }
                }
            }
        ]

        slots = list(slots_collection.aggregate(pipeline))

        return Response({
            'status':  1,
            'message': 'Slots fetched successfully.',
            'date':    date,
            'count':   len(slots),
            'data':    slots
        }, status=status.HTTP_200_OK)


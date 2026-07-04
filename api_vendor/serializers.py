from rest_framework import serializers
import re

# 1. Vendor Register Validation
class VendorRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100, required=True)
    slaughterhouse_name = serializers.CharField(max_length=255, required=True)
    city = serializers.CharField(max_length=100, required=True)
    capacity = serializers.IntegerField(required=True)
    country_code = serializers.CharField(max_length=5, required=True)
    mobile_number = serializers.CharField(max_length=15, required=True)

    def validate_mobile_number(self, value):
        clean_number = re.sub(r'\D', '', value)
        if len(clean_number) < 7 or len(clean_number) > 15:
            raise serializers.ValidationError("Invalid mobile number length.")
        return clean_number

# 2. Vendor Login Validation
class VendorLoginSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=5, required=True)
    mobile_number = serializers.CharField(max_length=15, required=True)

# 3. Vendor OTP Verification Validation
class VendorVerifyOTPSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=5, required=True)
    mobile_number = serializers.CharField(max_length=15, required=True)
    otp = serializers.CharField(max_length=6, required=True)


# Purane serializers ke neeche isko add karein
class AddAnimalSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True) # Yeh naya add kiya hai
    animal_category = serializers.CharField(max_length=50, required=True)
    breed = serializers.CharField(max_length=100, required=True)
    age = serializers.IntegerField(required=True)
    weight = serializers.FloatField(required=True)
    price = serializers.FloatField(required=True)
    # images = serializers.ListField(child=serializers.CharField(), required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class VendorProfileUpdateSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True) # Ab yeh mandatory field hai
    full_name = serializers.CharField(max_length=100, required=False)
    slaughterhouse_name = serializers.CharField(max_length=255, required=False)
    city = serializers.CharField(max_length=100, required=False)
    capacity = serializers.IntegerField(required=False)


class InventoryListSerializer(serializers.Serializer):
    _id = serializers.CharField()
    slaughterhouse_name = serializers.CharField()
    animal_category = serializers.CharField()
    breed = serializers.CharField()
    age = serializers.IntegerField()
    weight = serializers.FloatField()
    price = serializers.FloatField()
    images = serializers.ListField(child=serializers.CharField())
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
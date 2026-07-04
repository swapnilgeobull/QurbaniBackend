from rest_framework import serializers
import re

# 1. Register Ke Liye (Saari fields chahiye)
class UserRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100, required=True)
    city = serializers.CharField(max_length=100, required=True)
    country_code = serializers.CharField(max_length=5, required=True)
    mobile_number = serializers.CharField(max_length=15, required=True)

    def validate_mobile_number(self, value):
        clean_number = re.sub(r'\D', '', value)
        if len(clean_number) < 7 or len(clean_number) > 15:
            raise serializers.ValidationError("Invalid mobile number length.")
        return clean_number

# 2. Login Ke Liye (Sirf phone number chahiye)
class UserLoginSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=5, required=True)
    mobile_number = serializers.CharField(max_length=15, required=True)

# 3. OTP Verify Ke Liye
class VerifyOTPSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=5, required=True)
    mobile_number = serializers.CharField(max_length=15, required=True)
    otp = serializers.CharField(max_length=6, required=True)


class PlaceOrderSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)
    animal_id = serializers.CharField(required=True)
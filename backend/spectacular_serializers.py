from django.core.validators import URLValidator
from rest_framework import serializers

import backend.serializers
from backend.models import User, Category, Shop, ProductInfo, Product, ProductParameter, OrderItem, Order, Contact



class InputAccountConfirmationDataSerializer(serializers.Serializer):
    token = serializers.CharField()
    email = serializers.EmailField()


class UserDataSerializer(serializers.Serializer):
    first_name = serializers.CharField(source="User.first_name", required=False)
    last_name = serializers.CharField(source="User.last_name", required=False)
    password = serializers.CharField(source="User.password", required=False)
    email = serializers.EmailField(source="User.email", required=False)
    company = serializers.CharField(source="User.company", required=False)
    position = serializers.CharField(source="User.position", required=False)


class ContactSerializer(serializers.Serializer):
    city = serializers.CharField(source="Contact.city", required=True)
    street = serializers.CharField(source="Contact.street", required=True)
    house = serializers.CharField(source="Contact.house", required=False)
    structure = serializers.CharField(source="Contact.structure", required=False)
    building = serializers.CharField(source="Contact.building", required=False)
    apartment = serializers.CharField(source="Contact.apartment", required=False)
    phone = serializers.CharField(source="Contact.phone", required=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class ContactUpdateSerializer(ContactSerializer):
    id = serializers.CharField(required=True)
    city = serializers.CharField(source="Contact.city", required=False)
    street = serializers.CharField(source="Contact.street", required=False)
    house = serializers.CharField(source="Contact.house", required=False)
    structure = serializers.CharField(source="Contact.structure", required=False)
    building = serializers.CharField(source="Contact.building", required=False)
    apartment = serializers.CharField(source="Contact.apartment", required=False)
    phone = serializers.CharField(source="Contact.phone", required=False)


class PartnerStateSerializer(serializers.Serializer):
    state = serializers.ChoiceField(["True", "False"])


class PartnerUpdateSerializer(serializers.Serializer):
    url = serializers.CharField(validators=[URLValidator])
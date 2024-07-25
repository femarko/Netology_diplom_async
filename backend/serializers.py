# Верстальщик
from rest_framework import serializers

from backend.models import User, Category, Shop, ProductInfo, Product, ProductParameter, OrderItem, Order, Contact


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ('id', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'user', 'phone')
        read_only_fields = ('id',)
        extra_kwargs = {
            'user': {'write_only': True}
        }


class ContactPutSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=True)
    city = serializers.CharField(required=False)
    street = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)

    class Meta:
        model = Contact
        fields = ('id', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'user', 'phone')
        extra_kwargs = {
            'user': {'write_only': True}
        }


class RegisterAccountSerializer(serializers.ModelSerializer):
    contacts = ContactSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ('id', 'type', 'first_name', 'last_name', 'username', 'email', 'company', 'position', 'contacts')
        read_only_fields = ('id',)


class UserSerializer(serializers.ModelSerializer):
    contacts = ContactSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'username', 'email', 'company', 'position', 'contacts')
        read_only_fields = ('id',)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name',)
        read_only_fields = ('id',)


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ('id', 'name', 'state',)
        read_only_fields = ('id',)


class PartnerStateSerializer(ShopSerializer):
    state = serializers.BooleanField(required=True)

    def validate(self, attrs):
        if 'state' not in self.initial_data:
            raise serializers.ValidationError(detail="Field 'state' is required")
        return attrs

    class Meta:
        model = Shop
        fields = ('state',)


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = ('name', 'category',)


class ProductParameterSerializer(serializers.ModelSerializer):
    parameter = serializers.StringRelatedField()

    class Meta:
        model = ProductParameter
        fields = ('parameter', 'value',)


class ProductInfoSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_parameters = ProductParameterSerializer(read_only=True, many=True)

    class Meta:
        model = ProductInfo
        fields = ('id', 'model', 'product', 'shop', 'quantity', 'price', 'price_rrc', 'product_parameters',)
        read_only_fields = ('id',)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ('id', 'product_info', 'quantity', 'order',)
        read_only_fields = ('id',)
        extra_kwargs = {
            'order': {'write_only': True}
        }


class BasketPostSerializer(serializers.ModelSerializer):
    product_info_id = serializers.IntegerField()

    class Meta:
        model = OrderItem
        fields = ('product_info_id', 'quantity', 'order')


class OrderItemPutSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField()
    quantity = serializers.IntegerField()

    class Meta:
        model = OrderItem
        fields = ('id', 'quantity')


class OrderItemCreateSerializer(OrderItemSerializer):
    product_info = ProductInfoSerializer(read_only=True)


class OrderSerializer(serializers.ModelSerializer):
    ordered_items = OrderItemCreateSerializer(read_only=True, many=True)

    total_sum = serializers.IntegerField()
    contact = ContactSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ('id', 'ordered_items', 'state', 'dt', 'total_sum', 'contact',)
        read_only_fields = ('id',)


class OrderPostSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField()
    contact_id = serializers.IntegerField()

    class Meta:
        model = Order
        fields = ('id', 'contact_id')

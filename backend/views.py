from distutils.util import strtobool
from typing import Mapping, Iterable, Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiParameter, inline_serializer, \
    OpenApiExample, OpenApiResponse, OpenApiRequest

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Q, Sum, F
from django.http import JsonResponse

from rest_framework import serializers
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN, \
    HTTP_404_NOT_FOUND, HTTP_415_UNSUPPORTED_MEDIA_TYPE, HTTP_500_INTERNAL_SERVER_ERROR
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ParseError
from rest_framework.request import Request

from ujson import loads as load_json, JSONDecodeError

from celery.result import AsyncResult

from backend.models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, \
    Contact, ConfirmEmailToken
from backend.serializers import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, \
    OrderItemSerializer, OrderSerializer, ContactSerializer, RegisterAccountSerializer
from backend import spectacular_serializers
from backend.signals import new_user_registered, new_order
from backend.tasks import update_price_list

CONTENT_TYPES = ("application/json", "application/x-www-form-urlencoded", "multipart/form-data")


def json_parse(request: Request) -> JsonResponse | None:
    """JSON parse errors processing"""
    try:
        request_data_parsed: Mapping[str, str | int] = request.data
    except ParseError as err:
        return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)


def non_json_parse(request: Request, keys: Iterable) -> JsonResponse | None:
    """Non-JSON parse errors processing"""

    for key in keys:
        try:
            value_parsed = load_json(request.data.get(key))
        except JSONDecodeError as err:
            return JsonResponse({'Status': False, 'Errors': f"{err}. Expected values: digits without quotes"}, status=400)


def validate_keys_and_values(request: Request,
                             expected_keys: Iterable = None,
                             *args: Iterable,
                             **kwargs: Mapping) -> JsonResponse | None:
    errors_list: list[str] = []
    missing_keys_list: list[str] = []
    wrong_keys_list: list[str] = []
    json_wrong_values_list: list[str] = []
    non_json_wrong_values_list: list[str] = []

    for required_key in expected_keys:
        if required_key not in kwargs.keys():
            missing_keys_list.append(required_key)
    for key, value in kwargs.items():
        # if request.content_type == CONTENT_TYPES[0]:
        if key not in expected_keys:
            wrong_keys_list.append(key)
        if request.content_type == CONTENT_TYPES[0]:
            if type(value) is str and not value.isdigit():
                json_wrong_values_list.append(value)
        else:
            try:
                value_parsed = load_json(request.data.get(key))
            except JSONDecodeError as err:
                return JsonResponse({'Status': False, 'Errors': f"JSONDecodeError: '{err}'. "
                                                                f"Expected values: digits without quotes"},
                                    status=400)
            for item in value:
                if item.startswith(('"', "'")):
                    non_json_wrong_values_list.append(value)

    if missing_keys_list:
        errors_list.append(f'The following required keys are missing: {missing_keys_list}')
    if wrong_keys_list:
        errors_list.append(f'Wrong keys: {wrong_keys_list}. Expected keys are: {expected_keys}')
    if json_wrong_values_list:
        errors_list.append(f'Wrong values: {json_wrong_values_list}. Expected values: '
                           f'integers or a string format digits')
    if non_json_wrong_values_list:
        errors_list.append(f'Wrong values: {non_json_wrong_values_list}. Expected values: digits without quotes')

    if errors_list:
        return JsonResponse({'Status': False, 'Errors': errors_list}, status=400)


@extend_schema(tags=["users"])
@extend_schema_view(post=extend_schema(summary="Registration of a new account",
                                       request=spectacular_serializers.RegisterAccountSerializer,
                                       examples=[OpenApiExample(name="Example request body",
                                                                value={
                                                                    "type": "buyer",
                                                                    "first_name": "Luke",
                                                                    "last_name": "Skyworker",
                                                                    "username": "LSkyworker-2024",
                                                                    "email": "user@example.com",
                                                                    "password": "secretpass",
                                                                    "company": "Dream-team Ltd",
                                                                    "position": "Boss"
                                                                },
                                                                description='Required fields: "type", "first_name", '
                                                                            '"last_name", "email", "password", '
                                                                            '"company", "position"')]))
class RegisterAccount(APIView):
    """
    Для регистрации покупателей
    """

    # Регистрация методом POST

    def post(self, request, *args, **kwargs):
        """
            Process a POST request and create a new user.

            Args:
                request (Request): The Django request object.

            Returns:
                JsonResponse: The response indicating the status of the operation and any errors.
            """
        # проверяем обязательные аргументы
        if {'type', 'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):

            # проверяем пароль на сложность
            sad = 'asd'
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                # проверяем данные для уникальности имени пользователя

                register_account_serializer = RegisterAccountSerializer(data=request.data)
                if register_account_serializer.is_valid():
                    # сохраняем пользователя
                    user = register_account_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse({'Status': False, 'Errors': register_account_serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["users"])
@extend_schema_view(post=extend_schema(summary="Account confirmation",
                                       request=spectacular_serializers.ConfirmAccountSerializer,
                                       examples=[OpenApiExample(name="Example request body",
                                                                value={
                                                                    "token": "huik23kijnmk4jnkjhbnklpsefg9ij",
                                                                    "email": "user@example.com"
                                                                })]))
class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):
        """
                Подтверждает почтовый адрес пользователя.

                Args:
                - request (Request): The Django request object.

                Returns:
                - JsonResponse: The response indicating the status of the operation and any errors.
                """
        # проверяем обязательные аргументы
        if {'email', 'token'}.issubset(request.data):

            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан токен или email'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["users"])
@extend_schema_view(get=extend_schema(summary="Retrieve user data", request=UserSerializer),
                    post=extend_schema(summary="Update user data",
                                       request=spectacular_serializers.UserDataSerializer,
                                       examples=[OpenApiExample(
                                           name="Example request body",
                                           value={
                                               "first_name": "Luke",
                                               "last_name": "Skyworker",
                                               "username": "LSkyworker-2024",
                                               "email": "user@example.com",
                                               "password": "secretpass",
                                               "company": "Dream-team Ltd",
                                               "position": "Boss"
                                           },
                                           description="None of the fields is required."
                                       )]))
class AccountDetails(APIView):
    """
    A class for managing user account details.

    Methods:
    - get: Retrieve the details of the authenticated user.
    - post: Update the account details of the authenticated user.

    Attributes:
    - None
    """

    # получить данные
    def get(self, request: Request, *args, **kwargs):
        """
               Retrieve the details of the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the details of the authenticated user.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # Редактирование методом POST
    def post(self, request, *args, **kwargs):
        """
                Update the account details of the authenticated user.

                Args:
                - request (Request): The Django request object.

                Returns:
                - JsonResponse: The response indicating the status of the operation and any errors.
                """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        # validation of the filed names in the request body
        available_fields = UserSerializer.Meta.fields[1:]
        if not set(request.data.keys()).issubset(available_fields):
            return JsonResponse({'Status': False, 'Error': 'Wrong field name (names)'}, status=400)

        # проверяем обязательные аргументы

        if 'password' in request.data:
            errors = {}
            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                request.user.set_password(request.data['password'])

        # проверяем остальные данные
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True})
        else:
            return JsonResponse({'Status': False, 'Errors': user_serializer.errors})


@extend_schema(tags=["users"])
@extend_schema_view(post=extend_schema(summary="Login", request=spectacular_serializers.LoginSerializer))
class LoginAccount(APIView):
    """
    Класс для авторизации пользователей
    """

    # Авторизация методом POST
    def post(self, request, *args, **kwargs):
        """
                Authenticate a user.

                Args:
                    request (Request): The Django request object.

                Returns:
                    JsonResponse: The response indicating the status of the operation and any errors.
                """
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])

            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)

                    return JsonResponse({'Status': True, 'Token': token.key})

            return JsonResponse({'Status': False, 'Errors': 'Не удалось авторизовать'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["categories & products"])
@extend_schema_view(get=extend_schema(summary="Retrieve categories"))
class CategoryView(ListAPIView):
    """
    Класс для просмотра категорий
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


@extend_schema(tags=["shops & shopping"])
@extend_schema_view(get=extend_schema(summary="Retrieve shops"))
class ShopView(ListAPIView):
    """
    Класс для просмотра списка магазинов
    """
    queryset = Shop.objects.filter(state=True)
    serializer_class = ShopSerializer


@extend_schema(tags=["categories & products"])
@extend_schema_view(get=extend_schema(
    summary="Retrieve the product information based on the specified filters",
    parameters=[OpenApiParameter(name="shop_id", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
                OpenApiParameter(name="category_id", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY)]))
class ProductInfoView(APIView):
    """
        A class for searching products.

        Methods:
        - get: Retrieve the product information based on the specified filters.

        Attributes:
        - None
        """

    def get(self, request: Request, *args, **kwargs):
        """
               Retrieve the product information based on the specified filters.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the product information.
               """
        query = Q(shop__state=True)
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')

        if shop_id:
            query = query & Q(shop_id=shop_id)

        if category_id:
            query = query & Q(product__category_id=category_id)

        # фильтруем и отбрасываем дуликаты
        queryset = ProductInfo.objects.filter(
            query).select_related(
            'shop', 'product__category').prefetch_related(
            'product_parameters__parameter').distinct()

        serializer = ProductInfoSerializer(queryset, many=True)

        return Response(serializer.data)


@extend_schema(tags=["partners"])
@extend_schema_view(post=extend_schema(summary="Update the partner information",
                                       request=spectacular_serializers.PartnerUpdateSerializer))
class PartnerUpdate(APIView):
    """
    A class for updating partner information.

    Methods:
    - post: Update the partner information
    - get: Returns status of the celery task

    Attributes:
    - None
    """

    def post(self, request, *args, **kwargs):
        """
                Update the partner price list information.

                Args:
                - request (Request): The Django request object.

                Returns:
                - JsonResponse: The response indicating the status of the operation and any errors.
                """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)})
            else:
                user_id = request.user.id
                try:
                    asyns_result = update_price_list.delay(url, user_id)
                    task_id = asyns_result.id
                except:
                    return JsonResponse({'Status': False, 'Error': 'Error occured when updating price-list'})
                else:
                    return JsonResponse({'task_id': task_id})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["shops & shopping"])
class BasketView(APIView):
    """
    A class for managing the user's shopping basket.

    Methods:
    - get: Retrieve the items in the user's basket.
    - post: Add an item to the user's basket.
    - put: Update the quantity of an item in the user's basket.
    - delete: Remove an item from the user's basket.

    Attributes:
    - None
    """

    # todo: perhaps all this staff should be processed within a serializer?
    # todo: redesign -> give back content_type check to the view.method
    def get_items_list(self, request: Request, *args, **kwargs) -> [list[dict[str, [int | str]]] | JsonResponse]:
        """
        Check request body data
        """

        if request.content_type == "application/json":
            try:
                request_data: Request.data = request.data
            except ParseError as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            try:
                list_of_items_dicts: list[dict[str, [int | str]]] = request_data["items"]
            except KeyError as err:
                return JsonResponse({'Status': False, 'Errors': f"The required key {str(err)} is not provided"},
                                    status=400)
            errors_list: list = []
            wrong_keys_list: list = []
            wrong_values_list: list = []
            for items_dict in list_of_items_dicts:
                for key, value in items_dict.items():
                    if key not in args:
                        wrong_keys_list.append(key)
                    if type(value) is str and not value.isdigit():
                        wrong_values_list.append(value)
            if wrong_keys_list:
                errors_list.append(f'Wrong keys: {wrong_keys_list}. Required keys are: {args}')
            if wrong_values_list:
                errors_list.append(f'Wrong values: {wrong_values_list}. Required values must be integers '
                                   f'or a string format digits')
            if errors_list:
                return JsonResponse({'Status': False, 'Errors': errors_list}, status=400)
            return list_of_items_dicts  # todo: it is better to return None here
        else:
            try:
                list_of_items_dicts: list[dict[str, [int | str]]] = load_json(request.data.get("items"))
            except JSONDecodeError as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            else:
                return list_of_items_dicts

    # получить корзину
    @extend_schema(
        summary="Retrieve the items in the user's basket",
        responses={
            HTTP_200_OK: OpenApiResponse(response=OrderSerializer, description="Success"),
            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Forbidden",
                examples=[OpenApiExample(name="Log in required", value={"Status": False, "Error": "Log in required"})]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(response=None,
                                                            description="Any unexpected internal server errors")
        }
    )
    def get(self, request, *args, **kwargs):
        """
                Retrieve the items in the user's basket.

                Args:
                - request (Request): The Django request object.

                Returns:
                - Response: The response containing the items in the user's basket.
                """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        basket = Order.objects.filter(
            user_id=request.user.id, state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    # редактировать корзину
    @extend_schema(
        summary="Add an item to the user's basket",
        request=OpenApiRequest(
            request=spectacular_serializers.OrderItemSerializer,
            examples=[
                OpenApiExample(
                    name="Request body example",
                    value={"items": [{"product_info": 1, "quantity": 3}, {"product_info": 2, "quantity": 5}]}
                ),
            ],
        ),
        responses={
            HTTP_201_CREATED: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Created",
                examples=[OpenApiExample(name="Status: True", value={"Status": True, "Number of objects created": 3})]
            ),
            HTTP_400_BAD_REQUEST: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Bad Request",
                examples=[
                    OpenApiExample(name="ParseError",
                                   value={
                                       'Status': False,
                                       'Errors': 'JSON parse error - Expecting value: line 4 column 23 (char 43)'
                                   }),
                    OpenApiExample(name='Key "items" is required',
                                   value={'Status': False, 'Errors': "The required key 'items' is not provided"}),
                    OpenApiExample(
                        name="Wrong keys or values",
                        value={
                            "Status": False,
                            "Errors": [
                                "Wrong keys: ['product_inf']. Required keys are: ('product_info', 'quantity')",
                                "Wrong values: ['abc']. Required values must be integers or a string format digits"
                            ]
                        }
                    ),
                    OpenApiExample(name="JSONDecodeError",
                                   value={'Status': False, 'Errors': 'Expected object or value'}),
                    OpenApiExample(name="Integrity error",
                                   value={"Status": False, "Errors": "duplicate key value violates unique "
                                                                     "constraint \"unique_order_item\"\nDETAIL:  "
                                                                     "Key (order_id, product_info_id)=(1, 1) "
                                                                     "already exists.\n"}),
                    OpenApiExample(
                        name="Serializer error",
                        value={
                            "Status": False,
                            "Errors": "{'product_info': [ErrorDetail(string='Incorrect type. Expected pk value, "
                                      "received str.', code='incorrect_type')]}"
                        }
                    ),
                ]
            ),
            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Forbidden",
                examples=[
                    OpenApiExample(name="Log in required", value={'Status': False, 'Error': 'Log in required'})
                ]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(response=None,
                                                            description="Any unexpected internal server errors")
        }
    )
    def post(self, request, *args, **kwargs):
        """
               Add an items to the user's basket.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        required_keys_in_request_body: tuple = ("product_info", "quantity")
        get_items_list_result: [list[dict[str, [int | str]]] | JsonResponse] = self.get_items_list(
            request, *required_keys_in_request_body
        )
        if type(get_items_list_result) == JsonResponse:
            return get_items_list_result

        items_list: list[dict[str, [int | str]]] = get_items_list_result
        basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
        objects_created = 0
        for order_item in items_list:
            order_item.update({'order': basket.id})
            serializer = OrderItemSerializer(data=order_item)
            if serializer.is_valid():
                try:
                    serializer.save()
                except IntegrityError as err:
                    return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
                else:
                    objects_created += 1
            else:
                return JsonResponse({'Status': False, 'Errors': str(serializer.errors)}, status=400)
        return JsonResponse({'Status': True, 'Number of objects created': objects_created}, status=201)

    @extend_schema(
        summary="Remove an item from the user's basket",
        parameters=[
            OpenApiParameter(
                name="order_item_ids",
                location=OpenApiParameter.QUERY,
                description="Coma-separated set of order items IDs / Single order item ID",
                examples=[OpenApiExample(name="Example value", value="1,2,3")]
            ),
        ],
        responses={
            HTTP_200_OK: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                examples=[OpenApiExample(name="Success", value={'Status': True, 'Number of objects deleted': 1})]
            ),
            HTTP_400_BAD_REQUEST: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Error: Bad Request',
                examples=[
                    OpenApiExample(
                        name='No required argument',
                        value={'Status': False, 'Errors': "Query parameter 'order_item_ids' is required"})
                ]
            ),
            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Error: Forbidden',
                examples=[
                    OpenApiExample(
                        name='Log in required',
                        value={'Status': False, 'Error': 'Log in required'})
                ]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(response=None,
                                                            description="Any unexpected internal server errors")
        }
    )
    def delete(self, request, *args, **kwargs):
        """
                Remove  items from the user's basket.

                Args:
                - request (Request): The Django request object.

                Returns:
                - JsonResponse: The response indicating the status of the operation and any errors.
                """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.query_params.get('order_item_ids')
        if items_sting:
            items_list: list[str] = items_sting.split(',')
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            query = Q()
            objects_deleted = False
            for order_item_id in items_list:
                if order_item_id.isdigit():
                    query = query | Q(order_id=basket.id, id=order_item_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = OrderItem.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Number of objects deleted': deleted_count})
        return JsonResponse({'Status': False, 'Errors': 'Query parameter "order_item_ids" is required'}, status=400)

    @extend_schema(
        summary="Update the quantity of an item in the user's basket",
        request=OpenApiRequest(
            request=spectacular_serializers.OrderItemSerializer,
            examples=[
                OpenApiExample(name="Request body example",
                               value={"items": [{"id": 90, "quantity": 2}, {"id": 91, "quantity": 3}]})
            ]
        ),
        responses={
            HTTP_201_CREATED: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Success",
                examples=[
                    OpenApiExample(name="Status: True", value={'Status': True, 'Number of objects updated': 2}),
                ]
            ),
            HTTP_400_BAD_REQUEST: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Bad Request",
                examples=[
                    OpenApiExample(name="ParseError",
                                   value={
                                       'Status': False,
                                       'Errors': 'JSON parse error - Expecting value: line 4 column 13 (char 33)'
                                   }),
                    OpenApiExample(name='Key "items" is required',
                                   value={'Status': False, 'Errors': "The required key 'items' is not provided"}),
                    OpenApiExample(
                        name="Wrong keys or values",
                        value={
                            "Status": False,
                            "Errors": [
                                "Wrong keys: ['quantit']. Required keys are: ('id', 'quantity')",
                                "Wrong values: ['abc']. Required values must be integers or a string format digits"
                            ]
                        }
                    ),
                    OpenApiExample(name="JSONDecodeError",
                                   value={'Status': False, 'Errors': 'Expected object or value'}),

                ]
            ),

            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Forbidden",
                examples=[OpenApiExample(name="Log in required", value={'Status': False, 'Error': 'Log in required'})]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(response=None,
                                                            description="Any unexpected internal server errors")
        }
    )
    def put(self, request, *args, **kwargs):
        """
               Update the items in the user's basket.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        required_keys_in_request_body: tuple = ("id", "quantity")
        get_items_list_result: [list[dict[str, [int | str]]] | JsonResponse] = \
            self.get_items_list(request, *required_keys_in_request_body)
        if type(get_items_list_result) == JsonResponse:
            return get_items_list_result

        items_list: list[dict[str, [int | str]]] = get_items_list_result
        basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
        objects_updated = 0
        for order_item in items_list:
            objects_updated += OrderItem.objects.filter(order_id=basket.id, id=int(order_item.get('id'))).update(
                quantity=int(order_item.get('quantity')))
        return JsonResponse({'Status': True, 'Number of objects updated': objects_updated}, status=201)


@extend_schema(tags=["partners"])
@extend_schema_view(get=extend_schema(summary="Partners' price-list update task status"))
class PartnerUpdateTaskStatus(APIView):
    '''The celery-task status is represented as a response of a get-request to a specific url'''

    def get(self, request: Request, task_id: str) -> JsonResponse:
        task: AsyncResult = AsyncResult(task_id)
        return JsonResponse({'task_status': task.status})


@extend_schema(tags=["partners"])
@extend_schema_view(get=extend_schema(summary="Retrieve the state of a partner"),
                    post=extend_schema(summary="Update the state of a partner",
                                       request=spectacular_serializers.PartnerStateSerializer,
                                       examples=[OpenApiExample(name="Request body example",
                                                                value={"state": "True"},
                                                                description="case-insensitive true values: "
                                                                            "'y', 'yes', 't', 'true', 'on', '1'; "
                                                                            "case-insensitive false values: "
                                                                            "'n', 'no', 'f', 'false', 'off', '0'")]
                                       ))
class PartnerState(APIView):
    """
       A class for managing partner state.

       Methods:
       - get: Retrieve the state of a partner
       - post: Update the state of a partner

       Attributes:
       - None
       """

    # получить текущий статус
    def get(self, request, *args, **kwargs):
        """
               Retrieve the state of the partner.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the state of the partner.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        shop = request.user.shop
        serializer = ShopSerializer(shop)
        return Response(serializer.data)

    # изменить текущий статус
    def post(self, request, *args, **kwargs):
        """
               Update the state of a partner.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)
        state = request.data.get('state')
        if state:
            try:
                Shop.objects.filter(user_id=request.user.id).update(state=strtobool(state))
                return JsonResponse({'Status': True})
            except ValueError as error:
                return JsonResponse({'Status': False, 'Errors': str(error)})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["partners"])
@extend_schema_view(get=extend_schema(summary="Retrieve the orders associated with the authenticated partner"))
class PartnerOrders(APIView):
    """
    Класс для получения заказов поставщиками
     Methods:
    - get: Retrieve the orders associated with the authenticated partner.

    Attributes:
    - None
    """

    def get(self, request, *args, **kwargs):
        """
               Retrieve the orders associated with the authenticated partner.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the orders associated with the partner.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        order = Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


@extend_schema(tags=["contacts"])
@extend_schema_view(get=extend_schema(summary="Retrieve the contact information of the authenticated user",
                                      request=ContactSerializer),
                    post=extend_schema(summary="Create a new contact for the authenticated user",
                                       request=spectacular_serializers.ContactSerializer,
                                       examples=[OpenApiExample("Request example",
                                                                value={
                                                                    "city": "Test city",
                                                                    "street": "Test street",
                                                                    "house": "4",
                                                                    "structure": "3",
                                                                    "building": "2",
                                                                    "apartment": "1",
                                                                    "phone": "+01112223344"
                                                                },
                                                                description='Only "city", "street" and "phone" values '
                                                                            'are required.')]),
                    delete=extend_schema(summary="Delete the contact of the authenticated user",
                                         parameters=[OpenApiParameter(name="contact_ids",
                                                                      type=OpenApiTypes.STR,
                                                                      location=OpenApiParameter.QUERY,
                                                                      required=True,
                                                                      examples=[OpenApiExample('Example value',
                                                                                               value="1,2,3")])]),
                    put=extend_schema(summary="Partially or fully update of a contact record, relating to "
                                              "authenticated user",
                                      description="New values should be specified as request body parameters. In case "
                                                  "of partial update only parameters representing amended values "
                                                  "are needed.",
                                      request=spectacular_serializers.ContactUpdateSerializer,
                                      examples=[OpenApiExample(name="Example value",
                                                               value={"id": "1",
                                                                      "city": "Test city",
                                                                      "street": "Test street",
                                                                      "house": "4",
                                                                      "structure": "3",
                                                                      "building": "2",
                                                                      "apartment": "1",
                                                                      "phone": "+01112223344"})]))
class ContactView(APIView):
    """
       A class for managing contact information.

       Methods:
       - get: Retrieve the contact information of the authenticated user.
       - post: Create a new contact for the authenticated user.
       - put: Update the contact information of the authenticated user.
       - delete: Delete the contact of the authenticated user.

       Attributes:
       - None
       """

    # получить мои контакты
    def get(self, request, *args, **kwargs):
        """
               Retrieve the contact information of the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the contact information.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        contact = Contact.objects.filter(
            user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    # добавить новый контакт
    def post(self, request, *args, **kwargs):
        """
               Create a new contact for the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if {'city', 'street', 'phone'}.issubset(request.data):
            # request.data._mutable = True
            mutable_request_data = request.data.copy()
            # request.data.update({'user': request.user.id})
            mutable_request_data.update({'user': request.user.id})
            # serializer = ContactSerializer(data=request.data)
            serializer = ContactSerializer(data=mutable_request_data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    # удалить контакт
    def delete(self, request, *args, **kwargs):
        """
               Delete the contact of the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        # items_sting = request.data.get('items')
        items_sting = request.query_params.get('contact_ids')
        # items_sting = request.headers.get('items')

        if items_sting:
            items_list = items_sting.split(',')
            query = Q()
            objects_deleted = False
            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id=request.user.id, id=contact_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = Contact.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Удалено объектов': deleted_count})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    # редактировать контакт
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            """
                   Update the contact information of the authenticated user.

                   Args:
                   - request (Request): The Django request object.

                   Returns:
                   - JsonResponse: The response indicating the status of the operation and any errors.
                   """
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id=request.data['id'], user_id=request.user.id).first()
                print(contact)
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status': True})
                    else:
                        return JsonResponse({'Status': False, 'Errors': serializer.errors})
                else:
                    return JsonResponse({'Status': False, 'Errors': 'No contact with such id'})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["shops & shopping"])
class OrderView(APIView):
    """
    Класс для получения и размешения заказов пользователями
    Methods:
    - get: Retrieve the details of a specific order.
    - post: Create a new order.

    Attributes:
    - None
    """

    # получить мои заказы
    @extend_schema(
        summary="Retrieve the details of a specific order",
        request=OpenApiRequest(request=spectacular_serializers.OrderSerializer),
        responses={
            HTTP_200_OK: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="OK",
                examples=[
                    OpenApiExample(
                        name="Status: True",
                        value=[
                            {
                                "id": 3,
                                "ordered_items": [
                                    {
                                        "id": 53,
                                        "product_info": {
                                            "id": 1,
                                            "model": "apple/iphone/xs-max",
                                            "product": {
                                                "name": "Смартфон Apple iPhone XS Max 512GB (золотистый)",
                                                "category": "Смартфоны"
                                            },
                                            "shop": 1,
                                            "quantity": 14,
                                            "price": 110000,
                                            "price_rrc": 116990,
                                            "product_parameters": [
                                                {"parameter": "Диагональ (дюйм)", "value": "6.5"},
                                                {"parameter": "Разрешение (пикс)", "value": "2688x1242"},
                                                {"parameter": "Встроенная память (Гб)", "value": "512"},
                                                {"parameter": "Цвет", "value": "золотистый"}
                                            ]
                                        },
                                        "quantity": 3
                                    },
                                    {
                                        "id": 54,
                                        "product_info": {
                                            "id": 2,
                                            "model": "apple/iphone/xr",
                                            "product": {
                                                "name": "Смартфон Apple iPhone XR 256GB (красный)",
                                                "category": "Смартфоны"
                                            },
                                            "shop": 1,
                                            "quantity": 9,
                                            "price": 65000,
                                            "price_rrc": 69990,
                                            "product_parameters": [
                                                {"parameter": "Диагональ (дюйм)", "value": "6.1"},
                                                {"parameter": "Разрешение (пикс)", "value": "1792x828"},
                                                {"parameter": "Встроенная память (Гб)", "value": "256"},
                                                {"parameter": "Цвет", "value": "красный"}
                                            ]
                                        },
                                        "quantity": 5
                                    }
                                ],
                                "state": "new",
                                "dt": "2024-06-11T22:09:41.316030Z",
                                "total_sum": 655000,
                                "contact": {
                                    "id": 1,
                                    "city": "Test city",
                                    "street": "Test street",
                                    "house": "4",
                                    "structure": "3",
                                    "building": "2",
                                    "apartment": "1",
                                    "phone": "+01112223344"
                                }
                            }
                        ]
                    )
                ]
            ),
            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Forbidden",
                examples=[OpenApiExample(name="Log in required", value={'Status': False, 'Error': 'Log in required'})]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(response=None,
                                                            description="Any unexpected internal server errors")
        }
    )
    def get(self, request, *args, **kwargs):
        """
               Retrieve the details of user orders.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the details of the order.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        order = Order.objects.filter(
            user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    # разместить заказ из корзины
    @extend_schema(
        summary="Create a new order",
        request=OpenApiRequest(
            spectacular_serializers.OrderSerializer,
            examples=[OpenApiExample(name="Example request body", value={"order_id": "3", "contact_id": "2"})]
        ),
        responses={
            HTTP_201_CREATED: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Created",
                examples=[OpenApiExample(name="Created", value={'Status': True})]
            ),
            HTTP_400_BAD_REQUEST: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Bad Request",
                examples=[
                    OpenApiExample(
                        name="JSON parse error",
                        value={
                            'Status': False,
                            'Errors': 'JSON parse error - Expecting value: line 2 column 15 (char 16)'
                        }
                    ),
                    OpenApiExample(name="JSONDecodeError",
                                   value={"Status": False, "Errors": "Expected object or value"}),
                    OpenApiExample(
                        name="Wrong/missing keys, wrong value format",
                        value={
                            "Status": False,
                            "Errors": [
                                "The following required keys are missing: ['order_id']",
                                "Wrong keys: ['order_di']. Required keys are: ('order_id', 'contact_id')",
                                "Wrong values: ['']. Required values must be integers or a string format digits"
                            ]
                        }
                    ),
                    OpenApiExample(name="Wrong values",
                                   value={"Status": False,
                                          "Errors": ["Wrong values: [['\"3\"'], ['\"2\"']]. "
                                                     "Do not put values in quotes"]}),
                    OpenApiExample(
                        name="Order not found",
                        value={'Status': False, 'Errors': f"Order with 'order_id' = '1' does not exist"}
                    ),
                    OpenApiExample(
                        name="Wrong 'contact_id'",
                        value={
                            'Status': False,
                            'Errors': f"Wrong 'contact_id':"
                                      f" Key (contact_id)=(10) is not present in table \"backend_contact\".\n"
                        }
                    ),
                ]
            ),
            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Forbidden",
                examples=[OpenApiExample(name="Log in required", value={'Status': False, 'Error': 'Log in required'})]
            ),
            HTTP_404_NOT_FOUND: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Not found",
                examples=[
                    OpenApiExample(
                        name="Order is not found",
                        value={"Status": False, "Errors": "Order with 'order_id' = '1' does not exist"}
                    )
                ],
            ),
            HTTP_415_UNSUPPORTED_MEDIA_TYPE: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Error: Unsupported media type",
                examples=[
                    OpenApiExample(
                        name="Unsupported media type",
                        value={
                            'Status': False,
                            'Errors': f"Unsupported media type. Expected media types: ('application/json', "
                                      f"'application/x-www-form-urlencoded', 'multipart/form-data')"
                        }
                    )
                ]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(response=None,
                                                            description="Any unexpected internal server errors")

        }
    )
    def post(self, request, *args, **kwargs):
        """
               Put an order and send a notification.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        # content_types_mapping = [request.content_type.startswith(content_type) for content_type in CONTENT_TYPES]
        if True not in map(lambda content_type: request.content_type.startswith(content_type), CONTENT_TYPES):
            return JsonResponse(
                {'Status': False, 'Errors': f"Unsupported media type. Expected media types: {CONTENT_TYPES}"},
                status=415
            )

        expected_keys: tuple = ('order_id', 'contact_id')

        if request.content_type == CONTENT_TYPES[0]:
            json_parse_result = json_parse(request)
            if type(json_parse_result) == JsonResponse:
                return json_parse_result
            validation_result = validate_keys_and_values(request=request, expected_keys=expected_keys, **request.data)

            if type(validation_result) == JsonResponse:
                return validation_result
        else:
            non_json_parse_result = non_json_parse(request=request, keys=expected_keys)
            if type(non_json_parse_result) == JsonResponse:
                return non_json_parse_result
            validation_result = validate_keys_and_values(request=request, expected_keys=expected_keys, **request.data)
            if type(validation_result) == JsonResponse:
                return validation_result

        requested_order = Order.objects.filter(user_id=request.user.id, id=request.data['order_id'])
        if not requested_order:
            return JsonResponse(
                {'Status': False, 'Errors': f"Order with 'order_id' = '{request.data['order_id']}' does not exist"},
                status=404
            )
        try:
            is_updated = requested_order.update(contact_id=request.data['contact_id'], state='new')
        except IntegrityError as err:
            return JsonResponse({'Status': False, 'Errors': f"Wrong 'contact_id': {str(err).split(sep=': ')[1]}"},
                                status=400)
        else:
            if is_updated:
                new_order.send(sender=self.__class__, user_id=request.user.id)
                return JsonResponse({'Status': True}, status=201)

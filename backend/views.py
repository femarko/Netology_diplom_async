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
    OrderItemSerializer, OrderSerializer, ContactSerializer, RegisterAccountSerializer, OrderItemPutSerializer, \
    OrderPostSerializer, BasketPostSerializer
from backend import spectacular_serializers
from backend.custom_validators import json_parse, validate_keys_and_values, CONTENT_TYPES, validate_content_type, \
    get_request_items
from backend.signals import new_user_registered, new_order
from backend.tasks import update_price_list


@extend_schema(tags=["users"])
class RegisterAccount(APIView):
    """
    Для регистрации покупателей
    """

    # Регистрация методом POST

    @extend_schema(
        summary="Registration of a new account",
        request=OpenApiRequest(
            request=spectacular_serializers.RegisterAccountSerializer,
            examples=[
                OpenApiExample(
                    name="Example request body",
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
                    description='Required fields: "type", "first_name", "last_name", "email", "password", "company", '
                                '"position"'
                )
            ]
        ),
        responses={
            HTTP_201_CREATED: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Created',
                examples=[OpenApiExample(name='Created', value={'Status': True})]
            ),
            HTTP_400_BAD_REQUEST: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Error: Bad Request',
                examples=[
                    OpenApiExample(
                        name='Incompliant password',
                        value={
                            "Status": False,
                            "Errors": {
                                "password": ["This password is too short. It must contain at least 8 characters."]
                            }
                        }
                    ),
                    OpenApiExample(
                        name='Not unique email address',
                        value={
                            "Status": False,
                            "Errors": {"email": ["User with this email address already exists."]}
                        }
                    ),
                    OpenApiExample(
                        name='Required arguments have not been provided',
                        value={'Status': False, 'Errors': 'Required arguments have not been provided'}
                    )
                ]
            )
        }
    )
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
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}}, status=400)
            else:
                # проверяем данные для уникальности имени пользователя

                register_account_serializer = RegisterAccountSerializer(data=request.data)
                if register_account_serializer.is_valid():
                    # сохраняем пользователя
                    user = register_account_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    return JsonResponse({'Status': True}, status=201)
                else:
                    return JsonResponse({'Status': False, 'Errors': register_account_serializer.errors}, status=400)

        return JsonResponse({'Status': False, 'Errors': 'Required arguments have not been provided'}, status=400)


@extend_schema(tags=["users"])
class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    @extend_schema(
        summary="Account confirmation",
        request=OpenApiRequest(
            request=spectacular_serializers.ConfirmAccountSerializer,
            examples=[
                OpenApiExample(name="Example request body",
                               value={"token": "huik23kijnmk4jnkjhbnklpsefg9ij", "email": "user@example.com"})
            ]
        ),
        responses={
            HTTP_400_BAD_REQUEST: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Error: Bad request',
                examples=[
                    OpenApiExample(
                        name='Wrong token or email address',
                        value={'Status': False, 'Errors': 'Wrong token or email address'}
                    ),
                    OpenApiExample(
                        name='Required arguments have not been provided',
                        value={'Status': False, 'Errors': 'Required arguments have not been provided'}
                    )
                ]
            )
        }
    )
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
                return JsonResponse({'Status': False, 'Errors': 'Wrong token or email address'}, status=400)

        return JsonResponse({'Status': False, 'Errors': 'Required arguments have not been provided'}, status=400)


@extend_schema(tags=["users"])
@extend_schema_view(
    post=extend_schema())
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
    @extend_schema(
        summary="Retrieve user data",
        request=OpenApiRequest(request=UserSerializer),
        responses={
            HTTP_200_OK: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='OK',
                examples=[
                    OpenApiExample(
                        name='OK',
                        value={
                            "id": 3,
                            "first_name": "Luke",
                            "last_name": "Skyworker",
                            "username": "LSkyworker-2024",
                            "email": "user@example.com",
                            "company": "Dream-team Ltd",
                            "position": "Boss",
                            "contacts": [
                                {
                                    "id": 1,
                                    "city": "Test city",
                                    "street": "Test street",
                                    "house": "4",
                                    "structure": "3",
                                    "building": "2",
                                    "apartment": "1",
                                    "phone": "+01112223344"
                                }
                            ]
                        }
                    )
                ]
            ),
            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Error: Forbidden',
                examples=[OpenApiExample(name='Log in required', value={'Status': False, 'Error': 'Log in required'})]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(response=None,
                                                            description='Any unexpected internal server errors')
        }
    )
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
    @extend_schema(
        summary="Update user data",
        request=OpenApiRequest(
            request=spectacular_serializers.UserDataSerializer,
            examples=[
                OpenApiExample(
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
                )
            ]
        ),
        responses={
            HTTP_200_OK: OpenApiResponse(response=spectacular_serializers.ResponseSerializer,
                                         description="OK",
                                         examples=[OpenApiExample(name='OK', value={"Status": True})]),
            HTTP_400_BAD_REQUEST: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Error: Bad request',
                examples=[
                    OpenApiExample(
                        name='Not unique email address',
                        value={"Status": False, "Errors": {"email": ["User with this email address already exists."]}}
                    ),
                    OpenApiExample(
                        name='Incompliant password',
                        value={
                            "Status": False,
                            "Errors": {
                                "password": ["This password is too short. It must contain at least 8 characters."]
                            }
                        }
                    )
                ]
            ),
            HTTP_403_FORBIDDEN: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description='Error: Forbidden',
                examples=[OpenApiExample(
                    name='Log in required',
                    value={'Status': False, 'Error': 'Log in required'}
                )]
            ),
            HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(description="Any unexpected internal server errors")
        }
    )
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

        # password validation
        if 'password' in request.data:
            errors = {}
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}}, status=400)
            else:
                request.user.set_password(request.data['password'])

        # data validation
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True}, status=200)
        else:
            return JsonResponse({'Status': False, 'Errors': user_serializer.errors}, status=400)


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
                    return JsonResponse({'Status': True, 'Token': token.key}, status=200)
            return JsonResponse({'Status': False, 'Errors': 'Authentication is failed'}, status=403)
        return JsonResponse({'Status': False, 'Errors': 'Required arguments have not been provided'}, status=400)


@extend_schema(tags=["categories & products"])
@extend_schema_view(
    get=extend_schema(
        summary="Retrieve categories",
        responses={
            HTTP_200_OK: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="OK",
                examples=[
                    OpenApiExample(
                        name="OK",
                        value={
                            "count": 4,
                            "next": 3,
                            "previous": 1,
                            "results": [
                                [{"id": 5, "name": "Телевизоры"},
                                {"id": 224, "name": "Смартфоны"},
                                {"id": 15, "name": "Аксессуары"},
                                {"id": 1, "name": "Flash-накопители"}]
                            ]
                        }
                    )
                ]
            )
        }
    )
)
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
                    value={"items": [{"product_info_id": 1, "quantity": 3}, {"product_info_id": 2, "quantity": 5}]}
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
                    OpenApiExample(name="JSON parse error",
                                   value={
                                       'Status': False,
                                       'Errors': 'JSON parse error - Expecting value: line 4 column 23 (char 43)'
                                   }),
                    OpenApiExample(name="Wrong key",
                                   value={'Status': False, 'Errors': "Wrong key. Expected key: 'items'"}),
                    OpenApiExample(name="JSONDecodeError",
                                   value={
                                       "Status": False,
                                       "Errors": "No ':' found when decoding object value"
                                   }
                                   ),
                    OpenApiExample(
                        name="Serializer errors",
                        value={
                            "Status": False,
                            "Data provided": [{"product_info": 1, "quantity": 2}],
                            "Errors": [{"product_info_id": ["This field is required."]}]
                        }
                    ),
                    OpenApiExample(name="Integrity error",
                                   value={
                                       "Status": False,
                                       "Errors": "duplicate key value violates unique constraint \"unique_order_item\""
                                                 "\nDETAIL:  Key (order_id, product_info_id)=(7, 1) already exists.\n"
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
            HTTP_415_UNSUPPORTED_MEDIA_TYPE: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Unsupported media type",
                examples=[OpenApiExample(
                    name="Unsupported media type",
                    value={
                        'Status': False,
                        'Errors': f"Unsupported media type. Expected media types: {CONTENT_TYPES}"
                    }
                )]
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

        content_type_validation_result = validate_content_type(request=request, content_types=CONTENT_TYPES)
        if content_type_validation_result:
            return content_type_validation_result

        get_request_items_result: str | Iterable | Mapping = get_request_items(request=request,
                                                                               content_types=CONTENT_TYPES,
                                                                               expected_key="items")

        if type(get_request_items_result) is not JsonResponse:
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            data_to_validate = [{**order_item, **{'order': basket.id}} for order_item in get_request_items_result]
            serializer = BasketPostSerializer(data=data_to_validate, many=True)
            try:
                serializer.is_valid(raise_exception=True)
            except serializers.ValidationError:
                return JsonResponse(
                    {'Status': False, 'Data provided': get_request_items_result, 'Errors': serializer.errors},
                    status=400
                )
            except Exception as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            try:
                serializer.save()
            except IntegrityError as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            except Exception as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            else:
                return JsonResponse({'Status': True, 'Number of objects created': len(serializer.instance)},
                                    status=201)
        return get_request_items_result

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
            HTTP_200_OK: OpenApiResponse(
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
                    OpenApiExample(name="JSON parse error",
                                   value={
                                       'Status': False,
                                       'Errors': 'JSON parse error - Expecting value: line 4 column 23 (char 43)'
                                   }),
                    OpenApiExample(name="Wrong key",
                                   value={'Status': False, 'Errors': "Wrong key. Expected key: 'items'"}),
                    OpenApiExample(name="JSONDecodeError",
                                   value={
                                       "Status": False,
                                       "Errors": "No ':' found when decoding object value"
                                   }),
                    OpenApiExample(name="Serializer errors",
                                   value={
                                       "Status": False,
                                       "Data provided": [{"id": 1, "quantit": 2}],
                                       "Errors": [{"quantity": ["This field is required."]}]
                                   }),
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
                        value={
                            "Status": False,
                            "Data provided": [{"id": 1, "quantity": 2}],
                            "Errors": "Order items with IDs provided are not found"}
                    )
                ],
            ),
            HTTP_415_UNSUPPORTED_MEDIA_TYPE: OpenApiResponse(
                response=spectacular_serializers.ResponseSerializer,
                description="Unsupported media type",
                examples=[
                    OpenApiExample(
                        name="Unsupported media type",
                        value={
                            'Status': False, 'Errors': f"Unsupported media type. Expected media types: {CONTENT_TYPES}"
                        }
                    )
                ]
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

        content_type_validation_result = validate_content_type(request=request, content_types=CONTENT_TYPES)
        if content_type_validation_result:
            return content_type_validation_result

        get_request_items_result: list | Iterable | JsonResponse = get_request_items(request=request,
                                                                                     content_types=CONTENT_TYPES,
                                                                                     expected_key="items")

        if type(get_request_items_result) is not JsonResponse:
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            objects_updated = 0
            serializer = OrderItemPutSerializer(data=get_request_items_result, many=True)
            try:
                serializer.is_valid(raise_exception=True)
            except serializers.ValidationError:
                return JsonResponse(
                    {'Status': False, 'Data provided': serializer.initial_data, 'Errors': serializer.errors},
                    status=400
                )
            except Exception as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            for order_item in serializer.validated_data:
                objects_updated += OrderItem.objects.filter(order_id=basket.id, id=order_item.get('id')).update(
                    quantity=order_item.get('quantity')
                )
            if objects_updated != 0:
                return JsonResponse({'Status': True, 'Number of objects updated': objects_updated}, status=200)
            return JsonResponse(
                {'Status': False, 'Data provided': serializer.initial_data,
                 'Errors': 'Order items with IDs provided are not found'},
                status=404
            )
        return get_request_items_result


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
            examples=[OpenApiExample(name="Example request body", value={"id": 3, "contact_id": 1})]
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
                    OpenApiExample(name="JSON parse error",
                                   value={
                                       'Status': False,
                                       'Errors': 'JSON parse error - Expecting value: line 4 column 23 (char 43)'
                                   }),
                    OpenApiExample(name="Serializer errors",
                                   value={
                                       "Status": False,
                                       "Data provided": {"id_": "one", "contact_id": "'1'"},
                                       "Errors": {
                                           "id": ["This field is required."],
                                           "contact_id": ["A valid integer is required."]
                                       }
                                   }),
                    OpenApiExample(
                        name="Integrity error / Wrong 'contact_id'",
                        value={
                            "Status": False,
                            "Errors": "insert or update on table \"backend_order\" violates foreign key constraint "
                                      "\"backend_order_contact_id_fe3cc2b6_fk_backend_contact_id\"\nDETAIL:  "
                                      "Key (contact_id)=(7) is not present in table \"backend_contact\".\n"
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
                        value={"Status": False, "Errors": "Order with 'id' = '1' not found"}
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
                            "Status": False,
                            "Errors": "Unsupported media type. Expected media types: "
                                      "('application/json', 'application/x-www-form-urlencoded', 'multipart/form-data')"
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

        content_type_validation_result = validate_content_type(request=request, content_types=CONTENT_TYPES)
        if content_type_validation_result:
            return content_type_validation_result

        get_request_items_result = get_request_items(request=request, content_types=CONTENT_TYPES)
        if type(get_request_items_result) is not JsonResponse:
            serializer = OrderPostSerializer(data=request.data)
            try:
                serializer.is_valid(raise_exception=True)
            except serializers.ValidationError:
                return JsonResponse(
                    {'Status': False, 'Data provided': serializer.initial_data, 'Errors': serializer.errors},
                    status=400
                )
            except Exception as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            requested_order = Order.objects.filter(user_id=request.user.id, id=serializer.validated_data['id'])
            if not requested_order:
                return JsonResponse(
                    {
                        'Status': False,
                        'Errors': f"Order with 'id' = '{serializer.initial_data['id']}' not found"
                    },
                    status=404
                )
            try:
                is_updated = requested_order.update(contact_id=serializer.validated_data['contact_id'], state='new')
            except IntegrityError as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            except Exception as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            else:
                if is_updated:
                    new_order.send(sender=self.__class__, user_id=request.user.id)
                    return JsonResponse({'Status': True}, status=201)
        return get_request_items_result

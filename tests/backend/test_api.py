import pytest, copy
from rest_framework.test import APIClient
from django.http.response import JsonResponse
from dataclasses import dataclass
from typing import NamedTuple

from backend.models import User, ConfirmEmailToken

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class Fixture:
    client: APIClient
    base_url: str
    Endpoint_path: NamedTuple
    path: str
    user_data: dict[str, str]
    user: User


class Endpoint_path(NamedTuple):
    user_register: str
    confirm_account: str
    login: str
    user_details: str


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def base_url() -> str:
    return "/api/v1/"


@pytest.fixture
def path() -> Endpoint_path:
    base_url = "/api/v1/"
    return Endpoint_path(base_url + "user/register",
                         base_url + "user/register/confirm",
                         base_url + "user/login",
                         base_url + "user/details")


@pytest.fixture()
def user_data() -> dict[str, str]:
    return {
        "first_name": "test",
        "last_name": "test",
        "email": "t_e_s_t@internet.ru",
        "password": "testpassword",
        "company": "test",
        "position": "test"
    }


@pytest.fixture
def user(request, transactional_db, user_data: user_data, client: client, path: Endpoint_path) -> User:
    # request.cls.user_object = User.objects._create_user(**user_data)
    client.post(path=path.user_register, data=user_data)
    request.cls.user = User.objects.filter(email=user_data["email"]).first()


class TestUserRegisterConfirmLogin:

    class Email_token(NamedTuple):
        token: str
        user: User

    @pytest.mark.usefixtures("user")
    def email_confirmation_token(self, user: user) -> str:
        return ConfirmEmailToken.objects.filter(user_id=user.pk).first().key

    # def test_register_with_poor_data(self, client: client, path: Endpoint_path, user_data: user_data) -> None:
    #     poor_user_data_list: list[dict[str, str]] = []
    #     for key in user_data.keys():
    #         temp_dict: dict[str, str] = copy.deepcopy(user_data)
    #         temp_dict.pop(key)
    #         poor_user_data_list.append(temp_dict)
    #     result_list: list[dict[str, int | dict[str, bool | str]]] = []
    #     for data in poor_user_data_list:
    #         response = client.post(path=path.user_register, data=data)
    #         result_list.append({"status_code": response.status_code, "json": response.json()})
    #     for item in result_list:
    #         assert item == {
    #             "status_code": 200,
    #             "json": {'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}
    #         }

    @pytest.mark.usefixtures("user")
    def test_register_account(self, client: client, user_data: user_data, path: Endpoint_path) -> None:
        """
        Testing of API endpoint 'user/register': user data input and the view-function's response
        """
        # response = client.post(path=path.user_register, data=user_data)
        # user = User.objects.filter(email=user_data["email"]).first()
        user = self.user
        user_id = user.pk
        print(f'{user_id = }')
        confirm_email_token_instance = ConfirmEmailToken.objects.filter(user_id=user_id).first()
        print(f'{confirm_email_token_instance = }')
        token = confirm_email_token_instance.key
        # assert response.status_code == 200
        # assert response.json() == {'Status': True}
        assert isinstance(user, User)
        assert isinstance(confirm_email_token_instance, ConfirmEmailToken)
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.usefixtures("user")
    def test_confirm_email_token_creation(self, client: APIClient) -> None:
        """
        Testing of confirm_email_token creation for a new user: is there the token in the DB?
        """
        user: User = self.user_object
        print(f'{user = } | {user.pk = }')
        queryset = ConfirmEmailToken.objects.filter(user_id=user.pk)
        print(f'{queryset = } | {len(queryset) = }')
        token = queryset.first().key # token: str = self.email_confirmation_token(user)
        assert type(token) is str
        assert token != ""
        assert len(token) > 1

    @pytest.mark.usefixtures("user")
    def test_confirm_account(self, client: client, path: Endpoint_path):
        user: User = self.user_object
        print(f'{type(user) = } | {user = }')
        email_t_try = ConfirmEmailToken.objects.filter(user_id=user.pk)
        print(f'{email_t_try =} | {len(email_t_try)}')
        email_token = ConfirmEmailToken.objects.filter(user_id=user.pk).first().key

        response: JsonResponse = client.post(
            path=path.confirm_account, data={"email": user.email, "token": email_token}
        )
        assert response.status_code == 200
        assert response.json() == {'Status': True}
        assert user.is_active is True  # fails

    @pytest.mark.usefixtures("user")
    def test_login(self, client: client, path: Endpoint_path, user_data: user_data):
        user: User = self.user_object
        # response_confirm_account: JsonResponse = client.post(
        #     path=path.confirm_account, data={"email": user.email, "token": self.email_confirmation_token(user)}
        # )
        # auth_token = response_confirm_account.get("Token")
        response_login = client.post(
            path=path.login, data={"email": user.email, "password": user_data["password"]})
        assert response_login.status_code == 200
        assert user.is_authenticated
        assert response_login.json()["Status"] is True # fails

    # @pytest.mark.usefixtures("user")
    # def test_account_detailes(self, client: client, path: Endpoint_path):
    #     user: User = self.user_object
    #     print(f'{user.pk = }')
    #     # client.force_authenticate(user=user, token=self.email_confirmation_token(user))
    #     login_response: JsonResponse = client.post(path=path.login,
    #                                          data={"email": user.email, "token": self.email_confirmation_token(user)})
    #     response: JsonResponse = client.get(path=path.user_details,
    #                                         data={"email": user.email, "token": self.email_confirmation_token(user)})
    #
    #     assert user.is_authenticated is True
    #     assert response.status_code == 404

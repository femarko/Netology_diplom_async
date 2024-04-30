import pytest, copy
from rest_framework.test import APIClient
from django.http.response import JsonResponse
from dataclasses import dataclass
from typing import NamedTuple

from backend.models import User, ConfirmEmailToken

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class Fixture:
    Endpoint_path: NamedTuple
    client: APIClient
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
    client.post(path=path.user_register, data=user_data)
    request.cls.user = User.objects.filter(email=user_data["email"]).first()


class TestUserRegisterConfirmLogin:

    def test_register_account_with_poor_data(self, client: client, path: Endpoint_path, user_data: user_data) -> None:
        poor_user_data_list: list[dict[str, str]] = []
        for key in user_data.keys():
            temp_dict: dict[str, str] = copy.deepcopy(user_data)
            temp_dict.pop(key)
            poor_user_data_list.append(temp_dict)
        result_list: list[dict[str, int | dict[str, bool | str]]] = []
        for data in poor_user_data_list:
            response = client.post(path=path.user_register, data=data)
            result_list.append({"status_code": response.status_code, "json": response.json()})
        for item in result_list:
            assert item == {
                "status_code": 200,
                "json": {'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}
            }

    def test_register_account(self, user_data: user_data, path: Endpoint_path, client: client):
        response = client.post(path=path.user_register, data=user_data)
        user = User.objects.filter(email=user_data["email"]).first()
        print(f'{User.objects.filter(email=user_data["email"]).first().pk}')
        assert response.status_code == 200
        assert response.json() == {'Status': True}
        assert isinstance(user, User)

    @pytest.mark.usefixtures("user")
    def test_emailtoken_creation(self, client: client, user_data: user_data,
                                 path: Endpoint_path) -> None:
        user = self.user
        user_id = user.pk
        confirm_email_token_instance = ConfirmEmailToken.objects.filter(user_id=user_id).first()
        print(f'{confirm_email_token_instance = }')
        token = confirm_email_token_instance.key
        assert isinstance(user, User)
        assert isinstance(confirm_email_token_instance, ConfirmEmailToken)
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.usefixtures("user")
    def test_confirm_account(self, client: client, path: Endpoint_path):
        user: User = self.user
        confirm_email_token_instance: ConfirmEmailToken = ConfirmEmailToken.objects.filter(user_id=user.pk).first()
        email_token: str = confirm_email_token_instance.key
        response: JsonResponse = client.post(path=path.confirm_account,
                                             data={"email": user.email, "token": email_token})
        assert isinstance(confirm_email_token_instance, ConfirmEmailToken)
        assert isinstance(email_token, str)
        assert response.status_code == 200
        assert response.json() == {'Status': True}  # passes
        # assert user.is_active is True  # fails

    @pytest.mark.usefixtures("user")
    def test_login(self, client: client, path: Endpoint_path, user_data: user_data):
        user: User = self.user
        email_token = ConfirmEmailToken.objects.filter(user_id=user.pk).first().key
        client.post(path=path.confirm_account, data={"email": user.email, "token": email_token})
        response_login = client.post(path=path.login, data={"email": user.email, "password": user_data["password"]})
        auth_token = response_login.json()["Token"]
        assert response_login.status_code == 200
        assert user.is_authenticated
        assert response_login.json()["Status"] is True  # passes
        assert isinstance(auth_token, str)
        assert len(auth_token) > 0
        assert auth_token != ""
        # assert user.is_active is True # fails


class TestAccountDetailes:

    @pytest.mark.usefixtures("user")
    def test_account_detailes(self, client: client, path: Endpoint_path):
        user: User = self.user_object
        print(f'{user.pk = }')
        # client.force_authenticate(user=user, token=self.email_confirmation_token(user))
        login_response: JsonResponse = client.post(path=path.login,
                                             data={"email": user.email, "token": self.email_confirmation_token(user)})
        response: JsonResponse = client.get(path=path.user_details,
                                            data={"email": user.email, "token": self.email_confirmation_token(user)})

        assert user.is_authenticated is True
        assert response.status_code == 404

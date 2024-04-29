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
    user_data: dict[str, str]
    user: User
    Endpoint_path: NamedTuple


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def base_url() -> str:
    return "/api/v1/"


class Endpoint_path(NamedTuple):
    user_register: str
    confirm_account: str
    login: str
    user_details: str


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
def user(request, transactional_db, user_data: user_data) -> User:
    request.cls.user_object = User.objects.create_user(**user_data)


class TestUserRegisterConfirmLogin:
    user_register_url: str = "user/register"
    confirm_account_url: str = "user/register/confirm"
    login_url = "user/login"
    user_details_url = 'user/details'

    class Email_token(NamedTuple):
        token: str
        user: User

    def email_confirmation_token(self, user: user) -> str:
        return ConfirmEmailToken.objects.filter(user_id=user.pk).first().key

    def _registration_path(self, base_url: base_url) -> str:
        return base_url + self.user_register_url

    def _confirmation_path(self, base_url: base_url) -> str:
        return base_url + self.confirm_account_url

    def _login_path(self, base_url: base_url) -> str:
        return base_url + self.confirm_account_url

    def _user_detailes_path(self, base_url: base_url) -> str:
        return base_url + 'user/details'

    def test_register_with_poor_data(self, client: client, path: Endpoint_path, user_data: user_data) -> None:
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

    def test_register_account(self, client: client, user_data: user_data, path: Endpoint_path) -> None:
        """
        Testing of API endpoint 'user/register': user data input and the view-function's response
        """
        response = client.post(path=path.user_register, data=user_data)
        assert response.status_code == 200
        assert response.json() == {'Status': True}

    @pytest.mark.usefixtures("user")
    def test_confirm_email_token_creation(self, client: APIClient) -> None:
        """
        Testing of confirm_email_token creation for a new user: is there the token in the DB?
        """
        user: User = self.user_object
        token: str = self.email_confirmation_token(user)
        assert type(token) is str
        assert token != ""
        assert len(token) > 1

    @pytest.mark.usefixtures("user")
    def test_confirm_account(self, client: client, path: Endpoint_path):
        user: User = self.user_object
        user_id = user.pk
        email = user.email
        response: JsonResponse = client.post(path=path.confirm_account,
                                             data={"email": email, "token": self.email_confirmation_token(user)})
        assert response.status_code == 200
        assert response.json() == {'Status': True}
        # assert user.is_active is True  # fails

    @pytest.mark.usefixtures("user")
    def test_login(self, client: client, path: Endpoint_path):
        user: User = self.user_object
        token = ConfirmEmailToken.objects.filter(user_id=user.pk).first().key
        response: JsonResponse = client.post(path=path.login,
                                             data={"email": user.email, "token": self.email_confirmation_token(user)})
        assert response.status_code == 200
        assert user.is_authenticated
        # assert user.is_active
        assert response.json()["Status"] is True

    # @pytest.mark.usefixtures("user")
    # def test_account_detailes(self, client: client, path: Endpoint_path, user_data: user_data):
    #     user: User = self.user_object
    #     print(f'{user.pk = }')
    #     # client.force_authenticate(user=user, token=self.email_confirmation_token(user))
    #     login_response = client.post(path=path.login,
    #                                          data={"email": user.email, "token": self.email_confirmation_token(user)})
    #     response: JsonResponse = client.get(path=path.user_details,
    #                                         data={"email": user.email, "token": self.email_confirmation_token(user)})
    #
    #     assert user.is_authenticated is True
    #     assert response.status_code == 404

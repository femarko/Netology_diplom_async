import pytest, copy, pytest_ordering
from rest_framework.test import APIClient
from dataclasses import dataclass
from typing import TypeAlias, NewType, Type

from backend.models import User, ConfirmEmailToken

pytestmark = pytest.mark.django_db

@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def base_url() -> str:
    return "/api/v1/"


# @pytest.fixture
# def user_registration_poor_data(user_registration_data: dict[str, str]) -> list[dict[str, str]]:
#     poor_data_list = []
#     for key in user_registration_data.keys():
#         temp_dict = copy.deepcopy(user_registration_data)
#         temp_dict.pop(key)
#         poor_data_list.append(temp_dict)
#     return poor_data_list


# @pytest.fixture
# def user(user_registration_data: dict) -> User:
#     email = user_registration_data.get("email")
#     user_registration_data.pop("email")
#     return User.objects.create_user(email=email, **user_registration_data)


# @pytest.fixture
# def confirm_email_token(user: User) -> str:
#     return ConfirmEmailToken.objects.filter(user_id=user.pk)[0].key


@pytest.mark.django_db
class TestUserRegisterConfirmLogin:
    pytestmark = pytest.mark.django_db

    user_register_url = "user/register"
    confirm_account_url = 'user/register/confirm'

    @pytest.fixture(scope="class")
    def user_registration_data(self) -> dict[str, str]:
        return {
            "first_name": "test",
            "last_name": "test",
            "email": "t_e_s_t@internet.ru",
            "password": "testpassword",
            "company": "test",
            "position": "test"
        }

    @pytest.mark.django_db
    def user(self, user_registration_data):
        # user_data = {
        #     "first_name": "test",
        #     "last_name": "test",
        #     "email": "t_e_s_t@internet.ru",
        #     "password": "testpassword",
        #     "company": "test",
        #     "position": "test"
        # }
        user_object = User.objects.create_user(**user_registration_data)
        return user_object


    def _endpoint_path(self, base_url) -> str:
        return base_url + self.user_register_url

    def _endpoint_confirmation_path(self, base_url):
        return base_url + self.confirm_account_url

    def test_register_with_poor_data(self, client: APIClient, base_url, user_registration_data) -> None:

        poor_user_data_list = []
        for key in user_registration_data.keys():
            temp_dict = copy.deepcopy(user_registration_data)
            temp_dict.pop(key)
            poor_user_data_list.append(temp_dict)

        result_list = []
        for data in poor_user_data_list:
            response = client.post(path=self._endpoint_path(base_url), data=data)
            result_list.append({"status_code": response.status_code, "json": response.json()})
        for item in result_list:
            assert item == {
                "status_code": 200,
                "json": {'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}
            }

    def test_register_account(self, client: APIClient, user_registration_data: dict, base_url) -> None:
        """
        Testing of API endpoint 'user/register': user data input and the view-function's response
        """
        response = client.post(path=self._endpoint_path(base_url), data=user_registration_data)
        assert response.status_code == 200
        assert response.json() == {'Status': True}


    @pytest.mark.django_db
    def test_confirm_email_token_creation(self, client: APIClient, user_registration_data) -> None:
        """
        Testing of confirm_email_token creation for a new user: is there the token in the DB?
        """
        user_id = self.user(user_registration_data).pk
        token = ConfirmEmailToken.objects.filter(user_id=user_id)[0].key
        assert type(token) is str
        assert token != ""
        assert len(token) > 1

    def test_confirm_account(self, client: APIClient, base_url, user_registration_data):
        user = self.user(user_registration_data)
        user_id = user.pk
        token = ConfirmEmailToken.objects.filter(user_id=user_id)[0].key
        email = user.email
        response = client.post(path=self._endpoint_confirmation_path(base_url), data={"email": email, "token": token})
        print(f'{user_id=} {email=} {token=} {user.is_active=}')
        assert response.status_code == 200
        assert response.json() == {'Status': True}
        assert user.is_authenticated is True
        # assert user.is_active is True # fails


import pytest, copy, pytest_ordering
from rest_framework.test import APIClient
from dataclasses import dataclass
from typing import TypeAlias, NewType, Type

from backend.models import User, ConfirmEmailToken



@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def base_url() -> str:
    return "/api/v1/"


@pytest.fixture
def user_registration_data() -> dict[str, str]:
    user_register_data = {
        "first_name": "test",
        "last_name": "test",
        "email": "t_e_s_t@internet.ru",
        "password": "testpassword",
        "company": "test",
        "position": "test"
    }
    return user_register_data


@pytest.fixture
def user_registration_poor_data(user_registration_data: dict[str, str]) -> list[dict[str, str]]:
    poor_data_list = []
    for key in user_registration_data.keys():
        temp_dict = copy.deepcopy(user_registration_data)
        temp_dict.pop(key)
        poor_data_list.append(temp_dict)
    return poor_data_list


@pytest.fixture
def user(user_registration_data: dict) -> User:
    email = user_registration_data.get("email")
    user_registration_data.pop("email")
    return User.objects.create_user(email=email, **user_registration_data)


@pytest.fixture
def confirm_email_token(user: User) -> str:
    return ConfirmEmailToken.objects.filter(user_id=user.pk)[0].key


@pytest.mark.django_db
class TestRegisterAccount:
    endpoint_url = "user/register"

    def _endpoint_path(self, base_url) -> str:
        return base_url + self.endpoint_url

    def test_register_with_poor_data(self,
                                     user_registration_poor_data: list[dict[ str, str]],
                                     client: APIClient, base_url) -> None:
        result_list = []
        for data in user_registration_poor_data:
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

    def test_confirm_email_token_creation(self, client: APIClient, confirm_email_token: str) -> None:
        """
        Testing of confirm_email_token creation for a new user: is there the token in the DB?
        """
        token = confirm_email_token
        assert type(token) is str
        assert token != ""
        assert len(token) > 1


@pytest.mark.django_db
class TestConfirmAccount:
    endpoint_url = 'user/register/confirm'

    @staticmethod
    def _data(fixture_user: User, fixture_confirm_email_token: str) -> dict:
        return {"email": fixture_user.email, "token": fixture_confirm_email_token}

    def _endpoint_path(self, fixture_base_url: str) -> str:
        return fixture_base_url + self.endpoint_url

    def test_confirm_account(self, client: APIClient, base_url, user: User, confirm_email_token: str):
        response = client.post(path=self._endpoint_path(base_url), data=self._data(user, confirm_email_token))
        assert response.status_code == 200
        assert response.json() == {'Status': True}
        assert user.is_authenticated is True
        # assert user.is_active is True

    # def test_user_is_active(self, user: User):
    #     assert user.is_active is True


# @pytest.mark.run('last')
# class TestLoginAccount:
#
#     @pytest.mark.django_db
#     def test_login_with_correct_userdata(self, client, user_registration_data: dict):
#         data = {
#             "email": "t_e_s_t@internet.ru",
#             "password": "testpassword"
#         }
#         response = client.post(path=self.login_url, data=data)
#         assert response.status_code == 200
#         assert response.json().get("Status") is True
#         assert response.json().get("Token") is not None
#         assert len(response.json().get("Token")) > 1

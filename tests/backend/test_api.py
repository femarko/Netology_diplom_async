import pytest, copy, pytest_ordering
from rest_framework.test import APIClient
from dataclasses import dataclass
from typing import TypeAlias, NewType

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


# @pytest.mark.run('first')
class TestRegisterAccount:
    endpoint_url = "user/register"

    def endpoint_path(self, base_url) -> str:
        return base_url + self.endpoint_url

    @pytest.mark.django_db
    def test_register_with_poor_data(self,
                                     user_registration_poor_data: list[dict[ str, str]],
                                     client: APIClient, base_url) -> None:
        result_list = []
        for data in user_registration_poor_data:
            response = client.post(path=self.endpoint_path(base_url), data=data)
            result_list.append({"status_code": response.status_code, "json": response.json()})
        for item in result_list:
            assert item == {
                "status_code": 200,
                "json": {'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}
            }

    @pytest.mark.django_db
    def test_register_account(self, client: APIClient, user_registration_data: dict, base_url) -> None:
        """
        Testing of API endpoint 'user/register': input data and respective response
        """
        response = client.post(path=self.endpoint_path(base_url), data=user_registration_data)
        assert response.status_code == 200
        assert response.json() == {'Status': True}

    @pytest.mark.django_db
    def test_confirm_email_token_creation(self, client: APIClient, user: User) -> None:
        """
        Testing of confirm_email_token creation for a new user
        """
        token = ConfirmEmailToken.objects.filter(user_id=user.pk).key
        assert token is not None
        assert token != ""
        assert type(token) is str
        assert len(token) > 1


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

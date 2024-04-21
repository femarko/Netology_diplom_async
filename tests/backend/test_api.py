import pytest, copy
from rest_framework.test import APIClient


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user_registration_data() -> dict:
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
def user_registration_poor_data(user_registration_data: dict) -> list:
    poor_data_list = []
    for key in user_registration_data.keys():
        temp_dict = copy.deepcopy(user_registration_data)
        temp_dict.pop(key)
        poor_data_list.append(temp_dict)
    return poor_data_list


class TestRegisterAccount:
    registration_url = '/api/v1/user/register'

    @pytest.mark.django_db
    def test_register_account(self, client: APIClient, user_registration_data: dict):
        response = client.post(path=self.registration_url, data=user_registration_data)
        assert response.status_code == 200
        assert response.json() == {'Status': True}

    @pytest.mark.django_db
    def test_register_with_poor_data(self, user_registration_poor_data: list, client: APIClient):
        result_list = []
        for data in user_registration_poor_data:
            response = client.post(path=self.registration_url, data=data)
            result_list.append({"status_code": response.status_code, "json": response.json()})
        for item in result_list:
            assert item == {
                "status_code": 200,
                "json": {'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}
            }


class TestLoginAccount:
    login_url = '/api/v1/user/login'

    @pytest.mark.django_db
    def test_login_with_correct_userdata(self, client, user_registration_data):
        data = {
            "email": user_registration_data.get("email"),
            "password": user_registration_data.get("password")
        }
        response = client.post(path=self.login_url, data=data)
        assert response.status_code == 200
        assert response.json().get("Status") == True
        assert response.json().get("Token") is not None
        assert len(response.json().get("Token")) > 1

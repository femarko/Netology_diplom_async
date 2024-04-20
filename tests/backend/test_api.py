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


@pytest.mark.django_db
def test_register_account(client: APIClient, user_registration_data: dict):
    response = client.post(path='/api/v1/user/register', data=user_registration_data)
    assert response.status_code == 200
    assert response.json() == {'Status': True}


@pytest.mark.django_db
def test_register_with_poor_data(user_registration_poor_data: list, client: APIClient):
    result_dict = {}
    for data in user_registration_poor_data:
        response = client.post(path='/api/v1/user/register', data=data)
        result_dict.update({"status_code": response.status_code, "json": response.json()})
    assert result_dict == {
        "status_code": 200,
        "json": {'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}
    }



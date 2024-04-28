import pytest, copy
from rest_framework.test import APIClient
from dataclasses import dataclass

from backend.models import User, ConfirmEmailToken

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class Fixture:
    client: APIClient
    base_url: str
    user_data: dict[str, str]
    user: User


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def base_url() -> str:
    return "/api/v1/"


@pytest.fixture
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
def user(request, transactional_db, user_data: user_data):
        request.cls.user_object = User.objects.create_user(**user_data)


class TestUserRegisterConfirmLogin:
    user_register_url: str = "user/register"
    confirm_account_url: str = 'user/register/confirm'

    def _endpoint_registration_path(self, base_url: base_url) -> str:
        return base_url + self.user_register_url

    def _endpoint_confirmation_path(self, base_url: base_url):
        return base_url + self.confirm_account_url

    def test_register_with_poor_data(self, client: client, base_url: base_url, user_data: user_data) -> None:
        poor_user_data_list: list[dict[str, str]] = []
        for key in user_data.keys():
            temp_dict: dict[str, str] = copy.deepcopy(user_data)
            temp_dict.pop(key)
            poor_user_data_list.append(temp_dict)
        result_list: list[dict[str, int | dict[str, bool | str]]] = []
        for data in poor_user_data_list:
            response = client.post(path=self._endpoint_registration_path(base_url), data=data)
            result_list.append({"status_code": response.status_code, "json": response.json()})
        for item in result_list:
            assert item == {
                "status_code": 200,
                "json": {'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}
            }

    def test_register_account(self, client: client, user_data: user_data, base_url: base_url) -> None:
        """
        Testing of API endpoint 'user/register': user data input and the view-function's response
        """
        response = client.post(path=self._endpoint_registration_path(base_url), data=user_data)
        assert response.status_code == 200
        assert response.json() == {'Status': True}

    @pytest.mark.usefixtures("user")
    def test_confirm_email_token_creation(self, client: APIClient) -> None:
        """
        Testing of confirm_email_token creation for a new user: is there the token in the DB?
        """
        user: User = self.user_object
        user_id: int = user.pk
        token: str = ConfirmEmailToken.objects.filter(user_id=user_id)[0].key
        assert type(token) is str
        assert token != ""
        assert len(token) > 10


    @pytest.mark.usefixtures("user")
    def test_confirm_account(self, client: client, base_url: base_url):
        user: User = self.user_object
        user_id = user.pk
        token = ConfirmEmailToken.objects.filter(user_id=user_id)[0].key
        email = user.email
        response = client.post(path=self._endpoint_confirmation_path(base_url), data={"email": email, "token": token})
        assert response.status_code == 200
        assert response.json() == {'Status': True}
        assert user.is_active is True # fails

from typing import Mapping, Iterable, Any

from ujson import loads as load_json, JSONDecodeError

from django.http import JsonResponse
from rest_framework.exceptions import ParseError
from rest_framework.request import Request

CONTENT_TYPES = ("application/json", "application/x-www-form-urlencoded", "multipart/form-data")


def validate_content_type(request: Request, content_types: Iterable) -> None | JsonResponse:
    if True not in map(lambda content_type: request.content_type.startswith(content_type), content_types):
        return JsonResponse(
            {
                'Status': False,
                'Errors': f"{request.content_type} is unsupported media type. Expected media types: {content_types}"
            },
            status=415
        )


def json_parse(request: Request) -> JsonResponse | None:
    """JSON parse errors processing"""
    try:
        request.data
    except Exception as err:
        return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)


def get_request_items(request: Request, expected_key: str = None) -> str | Iterable | Mapping| JsonResponse:
    """

    Args:
        request ():
        content_types ():
        expected_key ():

    Returns:

    """
    if request.content_type == "application/json":
        parse_result: JsonResponse | None = json_parse(request=request)
        if parse_result:
            return parse_result
    if expected_key:
        if request.content_type == "application/json":
            try:
                request_items: list | Iterable | Mapping = request.data[expected_key]
            except KeyError:
                return JsonResponse({'Status': False, 'Errors': "Wrong key. Expected key: 'items'"}, status=400)
            else:
                return request_items
        else:
            try:
                request_items: list | Iterable | Mapping = load_json(request.data[expected_key])
            except KeyError:
                return JsonResponse({'Status': False, 'Errors': "Wrong key. Expected key: 'items'"}, status=400)
            except Exception as err:
                return JsonResponse({'Status': False, 'Errors': str(err)}, status=400)
            else:
                return request_items


def validate_keys_and_values(request: Request,
                             expected_keys: Iterable = None,
                             *args: Iterable,
                             **kwargs: Mapping) -> JsonResponse | None:
    errors_list: list[str] = []
    missing_keys_list: list[str] = []
    wrong_keys_list: list[str] = []
    json_wrong_values_list: list[str] = []
    json_decode_errors_list: list = []
    non_json_wrong_values_list: list[str] = []

    for required_key in expected_keys:
        if required_key not in kwargs.keys():
            missing_keys_list.append(required_key)
    for key, value in kwargs.items():
        if key not in expected_keys:
            wrong_keys_list.append(key)
        if request.content_type == CONTENT_TYPES[0]:
            if type(value) is str and not value.isdigit():
                json_wrong_values_list.append(value)
        else:
            try:
                value_parsed = load_json(request.data.get(key))
            except JSONDecodeError as err:
                json_decode_errors_list.append(str(err))
            for item in value:
                if item.startswith(('"', "'")):
                    non_json_wrong_values_list.append(value)

    if missing_keys_list:
        errors_list.append(f'The following required keys are missing: {missing_keys_list}')
    if wrong_keys_list:
        errors_list.append(f'Wrong keys: {wrong_keys_list}. Expected keys are: {expected_keys}')
    if json_wrong_values_list:
        errors_list.append(f'Wrong values: {json_wrong_values_list}. Expected values: '
                           f'integers or a string format digits')
    if json_decode_errors_list:
        errors_list.append(f'JSONDecodeErrors: {json_decode_errors_list}')
    if non_json_wrong_values_list:
        errors_list.append(f'Wrong values: {non_json_wrong_values_list}. Expected values: digits without quotes')

    if errors_list:
        return JsonResponse({'Status': False, 'Errors': errors_list}, status=400)

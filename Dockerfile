FROM python:3.10-alpine

COPY ./requirements.txt .
RUN pip install -r requirements.txt
RUN apk add --no-cache bash postgresql-client build-base postgresql-dev

COPY . /netology_dipl_async
WORKDIR /netology_dipl_async

CMD python3 manage.py migrate && python3 manage.py runserver 0.0.0.0:8000

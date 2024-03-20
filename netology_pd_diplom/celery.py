import os
from celery import Celery, shared_task
from rest_framework.request import Request
from backend.tasks import PartnerUpdate

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netology_pd_diplom.settings')

app = Celery('netology_pd_diplom')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


@shared_task(bind=True, ignore_result=True)
def update_pricelist_task(request):
    request = Request
    update_price_list_task = PartnerUpdate().post(request)
    return update_price_list_task.get()


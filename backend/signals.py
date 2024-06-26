from typing import Type

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created

from backend.models import ConfirmEmailToken, User
from .tasks import password_reset_token_created_task, new_user_registered_signal_task, new_order_signal_task

new_user_registered = Signal()

new_order = Signal()


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    """
    Отправляем письмо с токеном для сброса пароля
    When a token is created, an e-mail needs to be sent to the user
    :param sender: View Class that sent the signal
    :param instance: View Instance that sent the signal
    :param reset_password_token: Token Model Object
    :param kwargs:
    :return:
    """
    # get params for the celery-task
    reset_password_token_key = reset_password_token.key
    reset_password_token_user_email = reset_password_token.user.email
    # call the celery-task
    password_reset_token_created_task.delay(reset_password_token_key, reset_password_token_user_email)


@receiver(post_save, sender=User)
def new_user_registered_signal(sender: Type[User], instance: User, created: bool, **kwargs):
    """
     отправляем письмо с подтверждением почты
    """
    if created and not instance.is_active:
        # get params for the celery-task
        token, _ = ConfirmEmailToken.objects.get_or_create(user_id=instance.pk)
        token_key = token.key
        email = instance.email
        # call the celery-task
        new_user_registered_signal_task.delay(email, token_key)


@receiver(new_order)
def new_order_signal(user_id, **kwargs):
    """
    отправяем письмо при изменении статуса заказа
    """
    # get params for the celery-task
    user = User.objects.get(id=user_id)
    email = user.email
    # call the celery-task
    new_order_signal_task.delay(email)

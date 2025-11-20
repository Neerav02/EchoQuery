from celery import Celery

# 1. Create the Celery Application
# "worker" is just the name we give this instance.
# "broker" is the URL to RabbitMQ. Notice "guest:guest" and "broker" (the service name from docker-compose).
celery_app = Celery(
    "worker",
    broker="amqp://guest:guest@broker:5672//",
    backend="rpc://"
)

# 2. Configure standard settings
# This ensures that if the task returns a result, we can read it.
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
import boto3, json
from django.conf import settings

sqs = boto3.client(
    'sqs',
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)

def send_to_sqss(task_name, payload):
    """Send a JSON payload to SQS."""
    message = {
        "task": task_name,
        "payload": payload,
    }
    sqs.send_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        MessageBody=json.dumps(message)
    )

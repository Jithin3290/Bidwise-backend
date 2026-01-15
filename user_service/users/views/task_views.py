"""
Celery task status checking views
"""
from celery.result import AsyncResult
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_task_status(request, task_id):
    """Check the status of a Celery task"""
    try:
        result = AsyncResult(task_id)

        response_data = {
            'task_id': task_id,
            'status': result.status,
            'ready': result.ready(),
        }

        if result.ready():
            if result.successful():
                response_data['result'] = result.result
            else:
                response_data['error'] = str(result.info)
        else:
            response_data['message'] = 'Task is still processing...'

        return Response(response_data)

    except Exception as e:
        return Response(
            {'error': f'Failed to check task status: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
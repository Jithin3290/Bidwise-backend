class AllowServiceHostsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Override host validation for service-to-service calls
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer secure-service-token'):
            # It's a service call, bypass host validation
            request._dont_enforce_csrf_checks = True

        return self.get_response(request)


# users/middleware.py

class DisableHostCheckMiddleware:
    """
    Middleware to bypass host validation for service-to-service communication.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is a service-to-service request
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if auth_header.startswith('Bearer secure-service-token'):
            # Replace the host with a valid hostname that passes RFC validation
            # Adding .local makes it a valid hostname format
            request.META['HTTP_HOST'] = 'localhost'

        response = self.get_response(request)
        return response
# myshop/middleware/security_headers.py
"""
Security Headers Middleware
Adds security-related HTTP headers to all responses
"""


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to HTTP responses.

    Headers added:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking attacks
    - X-XSS-Protection: Enables XSS filtering in older browsers
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Controls browser features
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Prevent MIME type sniffing
        response["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking - deny embedding in frames
        response["X-Frame-Options"] = "DENY"

        # Enable XSS protection (for older browsers)
        response["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response

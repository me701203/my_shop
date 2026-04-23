from django.conf import settings
from django.utils import translation


def admin_language_middleware(get_response):
    def middleware(request):
        user_lang = request.session.get("django_language", settings.LANGUAGE_CODE)
        translation.activate(user_lang)
        response = get_response(request)
        translation.deactivate()
        return response

    return middleware

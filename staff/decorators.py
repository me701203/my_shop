import logging
from django.contrib.auth.decorators import login_required, user_passes_test

logger = logging.getLogger(__name__)


def staff_required(view_func):
    def wrapper(request, *args, **kwargs):
        # Check if user is authenticated and has staff access
        if not request.user.is_authenticated:
            logger.warning(
                f"Unauthorized staff access attempt: "
                f"user=anonymous, "
                f"path={request.path}, "
                f"ip={request.META.get('REMOTE_ADDR')}, "
                f"user_agent={request.META.get('HTTP_USER_AGENT', '')[:200]}"
            )
        elif not (
            request.user.is_active
            and (
                request.user.is_staff
                or request.user.groups.filter(name="Store Staff").exists()
            )
        ):
            logger.warning(
                f"Unauthorized staff access attempt: "
                f"user={request.user.username or request.user.email}, "
                f"path={request.path}, "
                f"ip={request.META.get('REMOTE_ADDR')}, "
                f"user_agent={request.META.get('HTTP_USER_AGENT', '')[:200]}"
            )

        # Use the original decorator chain
        decorated = user_passes_test(
            lambda u: u.is_active
            and (u.is_staff or u.groups.filter(name="Store Staff").exists()),
            login_url="/admin/login/",
        )(view_func)
        return login_required(decorated, login_url="/admin/login/")(
            request, *args, **kwargs
        )

    return wrapper

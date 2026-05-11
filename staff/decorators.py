from django.contrib.auth.decorators import login_required, user_passes_test


def staff_required(view_func):
    decorated = user_passes_test(
        lambda u: u.is_active
        and (u.is_staff or u.groups.filter(name="Store Staff").exists()),
        login_url="/admin/login/",
    )(view_func)
    return login_required(decorated, login_url="/admin/login/")

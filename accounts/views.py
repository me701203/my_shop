from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetView,
    PasswordResetConfirmView,
)
from .forms import (
    UserRegistrationForm,
    UserLoginForm,
    CustomPasswordResetForm,
    AddressForm,
)

from .models import Address


class UserRegistrationView(CreateView):
    """View for user registration"""

    form_class = UserRegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Registration successful. Please log in.")
        return response


class UserLoginView(LoginView):
    """View for user login"""

    form_class = UserLoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("shop:product_list")

    def form_valid(self, form):
        messages.success(self.request, f"Welcome, {form.get_user().username}!")
        return super().form_valid(form)


class UserLogoutView(LogoutView):
    """View for user logout"""

    next_page = reverse_lazy("shop:product_list")

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, "You have been logged out successfully.")
        return super().dispatch(request, *args, **kwargs)


class CustomPasswordResetView(PasswordResetView):
    """View for password reset request"""

    form_class = CustomPasswordResetForm
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.html"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        messages.success(
            self.request, "Password reset link has been sent to your email."
        )
        return super().form_valid(form)


@login_required
def profile_view(request):
    """View for user profile"""
    return render(request, "accounts/profile.html", {"user": request.user})


# I'm taking this one to orders app, it makes more sense there
# @login_required
# def order_history_view(request):
#     # Match orders by the logged-in user's email
#     orders = Order.objects.filter(
#         Q(user=request.user) | Q(email=request.user.email)
#     ).order_by("-created")

#     context = {
#         "orders": orders,
#     }
#     return render(request, "accounts/order_history.html", context)


@login_required
def address_list_view(request):
    """View for listing user's saved addresses"""
    addresses = Address.objects.filter(user=request.user)
    context = {
        "addresses": addresses,
    }
    return render(request, "accounts/addresses.html", context)


@login_required
def address_create_view(request):
    """View for creating a new address"""
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(
                request,
                f"Address '{address.label}' saved successfully."
                + (" This is now your default address." if address.is_default else ""),
            )
            return redirect("accounts:address_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Check if user has no addresses, make first one default
        has_addresses = Address.objects.filter(user=request.user).exists()
        initial_data = {"is_default": not has_addresses}
        form = AddressForm(initial=initial_data)

    context = {
        "form": form,
        "title": "Add New Address",
    }
    return render(request, "accounts/address_form.html", context)


@login_required
def address_edit_view(request, pk):
    """View for editing an existing address"""
    address = get_object_or_404(Address, pk=pk, user=request.user)

    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            updated_address = form.save()
            messages.success(
                request,
                f"Address '{updated_address.label}' updated successfully."
                + (
                    " This is now your default address."
                    if updated_address.is_default
                    else ""
                ),
            )
            return redirect("accounts:address_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AddressForm(instance=address)

    context = {
        "form": form,
        "title": "Edit Address",
        "address": address,
    }
    return render(request, "accounts/address_form.html", context)


@login_required
def address_delete_view(request, pk):
    """View for deleting an address"""
    address = get_object_or_404(Address, pk=pk, user=request.user)

    if request.method == "POST":
        address.delete()
        messages.success(request, "Address deleted successfully.")
        return redirect("accounts:address_list")

    context = {
        "address": address,
    }
    return render(request, "accounts/address_confirm_delete.html", context)

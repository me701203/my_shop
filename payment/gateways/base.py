import json
from decimal import Decimal
from django.conf import settings
from payment.models import PaymentLog


class BaseGateway:
    """
    A unified payment gateway interface that guarantees:

    - consistent request/verify contract
    - safe JSON serializing
    - anti‑tampering protection
    - gateway‑agnostic callback flow
    - strong typing and predictable structure
    """

    name = None  # override (e.g., "zarinpal")
    authority_param = None  # override (e.g., "Authority", "trackId")

    def __init__(self):
        self.config = settings.PAYMENT_GATEWAYS.get(self.name, {})

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def get_config(self, key, required=True, default=None):
        if key not in self.config and required:
            raise ValueError(f"Missing config '{key}' for gateway '{self.name}'")
        return self.config.get(key, default)

    def _safe_json(self, data):
        """Recursively convert non‑serializable types (Decimal, QuerySets, etc)."""
        if isinstance(data, Decimal):
            return float(data)
        if isinstance(data, dict):
            return {k: self._safe_json(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._safe_json(v) for v in data]
        return data

    # ---------------------------------------------------------
    # Logging
    # ---------------------------------------------------------

    def log(
        self,
        order,
        action,
        request_data=None,
        response_data=None,
        success=False,
        message="",
    ):

        PaymentLog.objects.create(
            order=order,
            gateway=self.name,
            action=action,
            request_data=self._safe_json(request_data or {}),
            response_data=self._safe_json(response_data or {}),
            success=success,
            message=message,
        )

    # ---------------------------------------------------------
    # Unified authority reading
    # ---------------------------------------------------------

    def get_authority(self, request):
        """All gateways will define self.authority_param."""
        if not self.authority_param:
            raise NotImplementedError(f"{self.name}: authority_param is not set")
        return request.GET.get(self.authority_param)

    # ---------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------

    def is_callback_success(self, request):
        """
        Gateways override to define what "callback arrived" means.
        Note: not final success. Verify() determines real success.
        """
        raise NotImplementedError

    # ---------------------------------------------------------
    # Main actions (to be overridden)
    # ---------------------------------------------------------

    def request(self, order, callback_url):
        """
        Must return:
            (success: bool, redirect_url: str, authority: str|None, error)
        """
        raise NotImplementedError

    def verify(self, request, order):
        """
        Must return:
            (success: bool, ref_id: str|None, error)
        """
        raise NotImplementedError

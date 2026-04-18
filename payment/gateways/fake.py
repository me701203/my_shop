import random
from django.urls import reverse
from .base import BaseGateway


class FakeGateway(BaseGateway):

    name = "fake"
    authority_param = "trackId"

    def is_callback_success(self, request):
        return request.GET.get("success") == "1"

    def request(self, order, callback_url):
        authority = str(random.randint(100000, 999999))

        self.log(
            order,
            "request",
            {"amount": float(order.get_total_cost())},
            {"authority": authority},
            True,
        )

        return True, reverse("payment:fake_bank", args=[order.id]), authority, None

    def verify(self, request, order):
        track_id = self.get_authority(request)
        self.log(order, "verify", {"trackId": track_id}, {}, True)
        return True, track_id, None

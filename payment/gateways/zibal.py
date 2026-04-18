import requests
from .base import BaseGateway


class ZibalGateway(BaseGateway):

    name = "zibal"
    authority_param = "trackId"

    def __init__(self):
        super().__init__()
        self.merchant = self.get_config("MERCHANT")
        self.request_url = self.get_config("REQUEST_URL")
        self.verify_url = self.get_config("VERIFY_URL")
        self.startpay_url = self.get_config("STARTPAY_URL")

    def is_callback_success(self, request):
        return bool(request.GET.get("trackId"))

    def request(self, order, callback_url):

        data = {
            "merchant": self.merchant,
            "amount": int(order.get_total_cost()),
            "callbackUrl": callback_url,
            "orderId": str(order.id),
            "description": f"Order {order.id}",
        }

        response = requests.post(self.request_url, json=data)
        result = response.json()

        self.log(order, "request", data, result)

        if result.get("result") == 100:
            track_id = result["trackId"]
            return True, f"{self.startpay_url}{track_id}", track_id, None

        return False, None, None, result

    def verify(self, request, order):

        track_id = self.get_authority(request)

        data = {
            "merchant": self.merchant,
            "trackId": track_id,
            "amount": int(order.get_total_cost()),
        }

        response = requests.post(self.verify_url, json=data)
        result = response.json()

        self.log(order, "verify", data, result)

        if result.get("result") == 100:
            ref_id = result.get("refNumber") or track_id  # sandbox fallback
            return True, ref_id, None

        return False, None, result

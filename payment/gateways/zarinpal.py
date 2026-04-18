import requests
from .base import BaseGateway


class ZarinpalGateway(BaseGateway):

    name = "zarinpal"
    authority_param = "Authority"

    def __init__(self):
        super().__init__()
        self.merchant_id = self.get_config("MERCHANT_ID")
        self.request_url = self.get_config("REQUEST_URL")
        self.verify_url = self.get_config("VERIFY_URL")
        self.startpay_url = self.get_config("STARTPAY_URL")

    def is_callback_success(self, request):
        return request.GET.get("Status") == "OK"

    def request(self, order, callback_url):

        data = {
            "merchant_id": self.merchant_id,
            "amount": int(order.get_total_cost()),
            "callback_url": callback_url,
            "description": f"Order {order.id}",
        }

        response = requests.post(self.request_url, json=data)
        result = response.json()
        self.log(order, "request", data, result)

        if result.get("data", {}).get("code") == 100:
            authority = result["data"]["authority"]
            return True, f"{self.startpay_url}{authority}", authority, None

        return False, None, None, result

    def verify(self, request, order):

        authority = self.get_authority(request)

        data = {
            "merchant_id": self.merchant_id,
            "amount": int(order.get_total_cost()),
            "authority": authority,
        }

        response = requests.post(self.verify_url, json=data)
        result = response.json()
        self.log(order, "verify", data, result)

        if result.get("data", {}).get("code") == 100:
            return True, result["data"]["ref_id"], None

        return False, None, result

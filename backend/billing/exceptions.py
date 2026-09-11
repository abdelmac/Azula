from rest_framework.exceptions import APIException


class BillingError(APIException):
    def __init__(self, code, status=400):
        self.code = code
        self.status_code = status
        super().__init__(detail=code, code=code)


class SubscriptionRequired(BillingError):
    def __init__(self):
        super().__init__("subscription_required", 402)

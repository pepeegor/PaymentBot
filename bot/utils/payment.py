import yookassa


def create_payment_link(mod: str, value: int, return_url: str):
    payment = yookassa.Payment.create({
        "amount": {
            "value": value,
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "description": mod,
        "capture": True
    })
    url = payment.confirmation.confirmation_url
    return url, payment.id


def check_payment(payment_id: str):
    payment = yookassa.Payment.find_one(payment_id)
    if payment.status == 'succeeded':
        return True

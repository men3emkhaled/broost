import unittest
from core.order_finance import validate_invoice_amounts


class InvoiceAmountTests(unittest.TestCase):
    def test_negative_nonfinite_and_excessive_discounts_are_rejected(self):
        for subtotal, fee, discount in ((100, 0, -1), (100, 0, 101), (float('nan'), 0, 0), (100, float('inf'), 0)):
            with self.subTest(values=(subtotal, fee, discount)), self.assertRaises(ValueError):
                validate_invoice_amounts(subtotal, fee, discount)

    def test_partial_cash_payment_is_not_counted_as_a_paid_invoice(self):
        with self.assertRaises(ValueError):
            validate_invoice_amounts(100, 0, 10, 50)
        self.assertEqual(validate_invoice_amounts(100, 0, 10, 0), 90)
        self.assertEqual(validate_invoice_amounts(100, 0, 10, 100), 90)

    def test_discount_never_consumes_driver_delivery_fee(self):
        self.assertEqual(validate_invoice_amounts(100, 20, 100), 20)
        with self.assertRaises(ValueError):
            validate_invoice_amounts(100, 20, 110)

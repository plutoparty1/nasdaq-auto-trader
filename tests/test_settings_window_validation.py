import unittest

import nasdaq_auto_trader.settings_window_dialog as settings_dialog


class SettingsWindowValidationTests(unittest.TestCase):
    def test_ai_quantity_limit_error_is_presented_in_korean(self):
        message = settings_dialog.localized_validation_message(
            ["ai_max_order_qty must be less than or equal to max_position_qty"]
        )

        self.assertEqual(
            message,
            "AI 최대 주문 수량은 최대 보유 수량보다 작거나 같아야 합니다.",
        )


if __name__ == "__main__":
    unittest.main()

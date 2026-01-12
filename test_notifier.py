import unittest
from src.utils.notifier import format_daily_briefing

class TestNotifier(unittest.TestCase):
    def test_format_length_limit(self):
        ai_items = [{"title": f"AI News {i}"} for i in range(20)]
        xr_items = [{"title": f"XR News {i}"} for i in range(20)]
        gov_items = [{"title": f"Gov Project {i}"} for i in range(20)]
        
        message = format_daily_briefing(ai_items, xr_items, gov_items, briefing_url="http://test.com", max_chars=500)
        
        self.assertLessEqual(len(message), 550)
        self.assertIn("VAAX", message)
        self.assertIn("http://test.com", message)
        
        # Check that we have some content
        self.assertIn("[AI] AI News 0", message)
        
        print("\n--- TEST OUTPUT (Length: {}) ---".format(len(message)))
        print(message)

    def test_format_empty(self):
        message = format_daily_briefing([], [], [], briefing_url="http://test.com")
        self.assertIn("VAAX", message)
        self.assertIn("http://test.com", message)
        # Body should be empty or just newlines
        
if __name__ == '__main__':
    unittest.main()

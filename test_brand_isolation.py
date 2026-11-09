import unittest
from platform_adapters.registry import PlatformRegistry

class TestBrandIsolation(unittest.TestCase):
    def test_unmapped_brands_cross_posting_blocked(self):
        """Brands 2, 3, 4 without social accounts must fail cleanly and never inherit accounts."""
        for brand_id in [2, 3, 4]:
            res_fb = PlatformRegistry.dispatch({'post_type': 'facebook', 'message': 'test', 'brand_id': brand_id})
            self.assertFalse(res_fb['success'])
            self.assertIn('No Facebook Page ID resolved', res_fb['error'])

            res_ig = PlatformRegistry.dispatch({'post_type': 'instagram', 'message': 'test', 'image_filename': 'test.jpg', 'brand_id': brand_id})
            self.assertFalse(res_ig['success'])
            self.assertIn('No Instagram User ID resolved', res_ig['error'])

            res_li = PlatformRegistry.dispatch({'post_type': 'linkedin', 'message': 'test', 'brand_id': brand_id})
            self.assertFalse(res_li['success'])
            self.assertIn('No LinkedIn account mapped', res_li['error'])

    def test_mapped_brands_resolve_correctly(self):
        """Brand 1, 5, 6 resolve only their own accounts."""
        # Brand 1 (Suite) -> FB & IG
        res_fb1 = PlatformRegistry.dispatch({'post_type': 'facebook', 'message': 'test', 'brand_id': 1})
        self.assertTrue(res_fb1['success'])

        res_ig1 = PlatformRegistry.dispatch({'post_type': 'instagram', 'message': 'test', 'image_filename': 'photo.png', 'brand_id': 1})
        self.assertTrue(res_ig1['success'])

        # Brand 5 (Phoenix) -> FB & IG
        res_fb5 = PlatformRegistry.dispatch({'post_type': 'facebook', 'message': 'test', 'brand_id': 5})
        self.assertTrue(res_fb5['success'])

        res_ig5 = PlatformRegistry.dispatch({'post_type': 'instagram', 'message': 'test', 'image_filename': 'photo.png', 'brand_id': 5})
        self.assertTrue(res_ig5['success'])

        # Brand 6 (GAATHA AI) -> FB only, IG fails
        res_fb6 = PlatformRegistry.dispatch({'post_type': 'facebook', 'message': 'test', 'brand_id': 6})
        self.assertTrue(res_fb6['success'])

        res_ig6 = PlatformRegistry.dispatch({'post_type': 'instagram', 'message': 'test', 'image_filename': 'photo.png', 'brand_id': 6})
        self.assertFalse(res_ig6['success'])
        self.assertIn('No Instagram User ID resolved', res_ig6['error'])

if __name__ == '__main__':
    unittest.main()


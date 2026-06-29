# tests/test_inventory_endpoints.py

import requests
import json
from typing import Dict, Any, List, Optional
import logging
from pprint import pprint
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

BASE_URL = "http://localhost:9096"  # Change to your server URL
API_PREFIX = "/esilo"  # Change if your API has a prefix

# Test data - based on the dummy data inserted
TEST_ORDERED_ITEM_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
TEST_CONSUMPTION_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
TEST_PRODUCT_IDS = [1, 2, 3, 4, 5, 10, 11, 21, 31, 36]

# ==================== TEST CLIENT ====================

class InventoryTestClient:
    """Test client for inventory endpoints"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make HTTP request and return JSON response"""
        url = f"{self.base_url}{API_PREFIX}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            logger.info(f"{method} {url} - Status: {response.status_code}")
            
            if response.status_code >= 400:
                logger.error(f"Error response: {response.text}")
            
            return {
                'status_code': response.status_code,
                'data': response.json() if response.text else {},
                'text': response.text
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return {
                'status_code': 500,
                'data': {},
                'error': str(e)
            }
    
    # ==================== RESERVATION ENDPOINTS ====================
    
    def reserve_inventory(self, items: List[Dict], item_type: str) -> Dict:
        """Test reserve inventory endpoint"""
        data = {
            'items': items,
            'item_type': item_type
        }
        return self._make_request('POST', '/inventory/reserve', data)
    
    def confirm_inventory(self, items: List[Dict], item_type: str) -> Dict:
        """Test confirm inventory endpoint"""
        data = {
            'items': items,
            'item_type': item_type
        }
        return self._make_request('POST', '/inventory/confirm', data)
    
    def release_inventory(self, items: List[Dict], item_type: str) -> Dict:
        """Test release inventory endpoint"""
        data = {
            'items': items,
            'item_type': item_type
        }
        return self._make_request('POST', '/inventory/release', data)
    
    def check_and_reserve(self, items: List[Dict], item_type: str) -> Dict:
        """Test check and reserve endpoint"""
        data = {
            'items': items,
            'item_type': item_type
        }
        return self._make_request('POST', '/inventory/check-and-reserve', data)
    
    # ==================== QUERY ENDPOINTS ====================
    
    def get_stock_status(self, product_id: int) -> Dict:
        """Test get stock status endpoint"""
        return self._make_request('GET', f'/inventory/stock/{product_id}')
    
    def get_bulk_stock_status(self, product_ids: List[int]) -> Dict:
        """Test bulk stock status endpoint"""
        data = {'product_ids': product_ids}
        return self._make_request('POST', '/inventory/stock/bulk', data)
    
    def get_inventory_summary(self, product_id: int) -> Dict:
        """Test inventory summary endpoint"""
        return self._make_request('GET', f'/inventory/summary/{product_id}')
    
    def get_available_quantity(self, product_id: int) -> Dict:
        """Test available quantity endpoint"""
        return self._make_request('GET', f'/inventory/available/{product_id}')
    
    # ==================== BULK OPERATIONS ====================
    
    def bulk_reserve(self, ordered_items: List[Dict], consumptions: List[Dict]) -> Dict:
        """Test bulk reserve endpoint"""
        data = {
            'ordered_items': ordered_items,
            'consumptions': consumptions
        }
        return self._make_request('POST', '/inventory/bulk/reserve', data)
    
    def bulk_confirm(self, ordered_items: List[Dict], consumptions: List[Dict]) -> Dict:
        """Test bulk confirm endpoint"""
        data = {
            'ordered_items': ordered_items,
            'consumptions': consumptions
        }
        return self._make_request('POST', '/inventory/bulk/confirm', data)
    
    def bulk_release(self, ordered_items: List[Dict], consumptions: List[Dict]) -> Dict:
        """Test bulk release endpoint"""
        data = {
            'ordered_items': ordered_items,
            'consumptions': consumptions
        }
        return self._make_request('POST', '/inventory/bulk/release', data)
    
    def health_check(self) -> Dict:
        """Test health check endpoint"""
        return self._make_request('GET', '/inventory/health')


# ==================== TEST FUNCTIONS ====================

def test_health_check(client: InventoryTestClient):
    """Test health check endpoint"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Health Check")
    logger.info("="*60)
    
    result = client.health_check()
    
    if result['status_code'] == 200:
        logger.info(f"✅ Health check passed: {result['data']}")
    else:
        logger.error(f"❌ Health check failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_get_stock_status(client: InventoryTestClient):
    """Test getting stock status for products"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Get Stock Status")
    logger.info("="*60)
    
    results = []
    
    for product_id in TEST_PRODUCT_IDS[:5]:  # Test first 5 products
        logger.info(f"\nGetting stock status for product {product_id}...")
        result = client.get_stock_status(product_id)
        
        results.append({
            'product_id': product_id,
            'status': result['status_code'],
            'data': result['data']
        })
        
        if result['status_code'] == 200:
            data = result['data']
            logger.info(f"✅ Product {product_id}:")
            logger.info(f"   Stock: {data.get('stock_quantity')}")
            logger.info(f"   Reserved: {data.get('reserved_quantity')}")
            logger.info(f"   Available: {data.get('available_quantity')}")
            logger.info(f"   Version: {data.get('version')}")
        else:
            logger.error(f"❌ Failed to get stock status: {result.get('error', 'Unknown error')}")
    
    return results


def test_bulk_stock_status(client: InventoryTestClient):
    """Test bulk stock status endpoint"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Bulk Stock Status")
    logger.info("="*60)
    
    product_ids = TEST_PRODUCT_IDS[:10]
    logger.info(f"Checking stock for {len(product_ids)} products...")
    
    result = client.get_bulk_stock_status(product_ids)
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Retrieved stock status for {len(data)} products")
        for product_id, stock in list(data.items())[:5]:  # Show first 5
            logger.info(f"   Product {product_id}: {stock.get('available_quantity')} available")
    else:
        logger.error(f"❌ Failed to get bulk stock status: {result.get('error', 'Unknown error')}")
    
    return result


def test_reserve_ordered_items(client: InventoryTestClient):
    """Test reserving inventory for ordered items"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Reserve Ordered Items")
    logger.info("="*60)
    
    # Test cases - reserve quantities for various ordered items
    test_cases = [
        # Ordered item 1 (Surgical Masks) - reserve 50
        {'id': 1, 'quantity': 50},
        # Ordered item 2 (Nitrile Gloves) - reserve 20
        {'id': 2, 'quantity': 20},
        # Ordered item 7 (Paracetamol) - reserve 10
        {'id': 7, 'quantity': 10},
    ]
    
    logger.info(f"Reserving items: {test_cases}")
    result = client.reserve_inventory(test_cases, 'ordered_item')
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Reservation result:")
        logger.info(f"   Success: {data.get('success')}")
        logger.info(f"   Success count: {data.get('success_count')}")
        logger.info(f"   Failed count: {data.get('failed_count')}")
        
        for item in data.get('success_items', []):
            logger.info(f"   ✅ Reserved {item.get('reserved_quantity')} of ordered item {item.get('ordered_item_id')}")
        
        for item in data.get('failed_items', []):
            logger.info(f"   ❌ Failed: {item.get('reason')}")
    else:
        logger.error(f"❌ Reservation failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_reserve_consumptions(client: InventoryTestClient):
    """Test reserving inventory for consumptions"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Reserve Consumptions")
    logger.info("="*60)
    
    # Test cases - reserve quantities for various consumptions
    test_cases = [
        # Consumption 1 (Surgical Masks) - reserve 100
        {'id': 1, 'quantity': 100},
        # Consumption 2 (Nitrile Gloves) - reserve 30
        {'id': 2, 'quantity': 30},
        # Consumption 3 (Isopropyl Alcohol) - reserve 20
        {'id': 3, 'quantity': 20},
    ]
    
    logger.info(f"Reserving consumptions: {test_cases}")
    result = client.reserve_inventory(test_cases, 'consumption')
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Reservation result:")
        logger.info(f"   Success: {data.get('success')}")
        logger.info(f"   Success count: {data.get('success_count')}")
        logger.info(f"   Failed count: {data.get('failed_count')}")
        
        for item in data.get('success_items', []):
            logger.info(f"   ✅ Reserved {item.get('reserved_quantity')} of consumption {item.get('consumption_id')}")
        
        for item in data.get('failed_items', []):
            logger.info(f"   ❌ Failed: {item.get('reason')}")
    else:
        logger.error(f"❌ Reservation failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_check_and_reserve(client: InventoryTestClient):
    """Test check and reserve endpoint"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Check and Reserve")
    logger.info("="*60)
    
    # Test with ordered items
    test_cases = [
        {'id': 1, 'quantity': 10},
        {'id': 2, 'quantity': 5},
        {'id': 999, 'quantity': 1},  # Non-existent item - should fail
    ]
    
    logger.info(f"Checking and reserving: {test_cases}")
    result = client.check_and_reserve(test_cases, 'ordered_item')
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Check and reserve result:")
        logger.info(f"   Overall success: {data.get('success')}")
        
        for item in data.get('items', []):
            status = "✅" if item.get('success') else "❌"
            logger.info(f"   {status} Item {item.get('id')}: {item.get('reason', 'Success')}")
    else:
        logger.error(f"❌ Check and reserve failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_confirm_ordered_items(client: InventoryTestClient):
    """Test confirming inventory for ordered items"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Confirm Ordered Items")
    logger.info("="*60)
    
    # First, reserve some items
    reserve_items = [
        {'id': 3, 'quantity': 30},
        {'id': 4, 'quantity': 10},
    ]
    
    logger.info("First reserving items...")
    reserve_result = client.reserve_inventory(reserve_items, 'ordered_item')
    
    if reserve_result['status_code'] != 200:
        logger.error("❌ Failed to reserve items for confirmation test")
        return reserve_result
    
    # Now confirm them
    logger.info("Now confirming items...")
    confirm_items = [
        {'id': 3, 'quantity': 30},
        {'id': 4, 'quantity': 10},
    ]
    
    result = client.confirm_inventory(confirm_items, 'ordered_item')
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Confirmation result:")
        logger.info(f"   Success: {data.get('success')}")
        logger.info(f"   Success count: {data.get('success_count')}")
        logger.info(f"   Failed count: {data.get('failed_count')}")
        
        for item in data.get('success_items', []):
            logger.info(f"   ✅ Confirmed {item.get('confirmed_quantity')} of ordered item {item.get('ordered_item_id')}")
    else:
        logger.error(f"❌ Confirmation failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_release_ordered_items(client: InventoryTestClient):
    """Test releasing inventory for ordered items"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Release Ordered Items")
    logger.info("="*60)
    
    # First, reserve some items
    reserve_items = [
        {'id': 5, 'quantity': 15},
        {'id': 6, 'quantity': 5},
    ]
    
    logger.info("First reserving items...")
    reserve_result = client.reserve_inventory(reserve_items, 'ordered_item')
    
    if reserve_result['status_code'] != 200:
        logger.error("❌ Failed to reserve items for release test")
        return reserve_result
    
    # Now release them
    logger.info("Now releasing items...")
    release_items = [
        {'id': 5, 'quantity': 15},
        {'id': 6, 'quantity': 5},
    ]
    
    result = client.release_inventory(release_items, 'ordered_item')
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Release result:")
        logger.info(f"   Success: {data.get('success')}")
        logger.info(f"   Success count: {data.get('success_count')}")
        logger.info(f"   Failed count: {data.get('failed_count')}")
        
        for item in data.get('success_items', []):
            logger.info(f"   ✅ Released {item.get('released_quantity')} of ordered item {item.get('ordered_item_id')}")
    else:
        logger.error(f"❌ Release failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_bulk_operations(client: InventoryTestClient):
    """Test bulk operations"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Bulk Operations")
    logger.info("="*60)
    
    # Test bulk reserve
    logger.info("\nTesting bulk reserve...")
    ordered_items = [
        {'id': 8, 'quantity': 10},
        {'id': 9, 'quantity': 5},
    ]
    consumptions = [
        {'id': 4, 'quantity': 15},
        {'id': 5, 'quantity': 10},
    ]
    
    result = client.bulk_reserve(ordered_items, consumptions)
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Bulk reserve result:")
        logger.info(f"   Overall success: {data.get('overall_success')}")
        
        if data.get('ordered_items'):
            logger.info(f"   Ordered items success: {data['ordered_items'].get('success_count')}/{data['ordered_items'].get('success_count') + data['ordered_items'].get('failed_count')}")
        if data.get('consumptions'):
            logger.info(f"   Consumptions success: {data['consumptions'].get('success_count')}/{data['consumptions'].get('success_count') + data['consumptions'].get('failed_count')}")
    else:
        logger.error(f"❌ Bulk reserve failed: {result.get('error', 'Unknown error')}")
    
    # Test bulk release
    logger.info("\nTesting bulk release...")
    result = client.bulk_release(ordered_items, consumptions)
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Bulk release result:")
        logger.info(f"   Overall success: {data.get('overall_success')}")
    else:
        logger.error(f"❌ Bulk release failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_insufficient_stock_scenario(client: InventoryTestClient):
    """Test insufficient stock scenario"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Insufficient Stock Scenario")
    logger.info("="*60)
    
    # Try to reserve more than available for a product
    # Product 1 has 5000 stock, so this should be fine
    # But we'll try to reserve 6000 to test failure
    test_cases = [
        {'id': 1, 'quantity': 6000},  # Product 1 only has 5000
    ]
    
    logger.info(f"Attempting to reserve {test_cases[0]['quantity']} units when only 5000 available...")
    result = client.reserve_inventory(test_cases, 'ordered_item')
    
    if result['status_code'] == 200:
        data = result['data']
        if data.get('success_count') == 0:
            logger.info(f"✅ Correctly failed due to insufficient stock")
            logger.info(f"   Reason: {data.get('failed_items', [{}])[0].get('reason')}")
        else:
            logger.warning(f"⚠️ Unexpected success: {data}")
    else:
        logger.error(f"❌ Test failed: {result.get('error', 'Unknown error')}")
    
    return result


def test_invalid_scenarios(client: InventoryTestClient):
    """Test invalid scenarios"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Invalid Scenarios")
    logger.info("="*60)
    
    # Test 1: Non-existent ordered item
    logger.info("\n1. Testing non-existent ordered item...")
    result = client.reserve_inventory([{'id': 999, 'quantity': 1}], 'ordered_item')
    if result['status_code'] == 200:
        data = result['data']
        if data.get('failed_count') == 1:
            logger.info("✅ Correctly failed for non-existent item")
        else:
            logger.warning(f"⚠️ Unexpected result: {data}")
    
    # Test 2: Negative quantity (should be caught by validation)
    logger.info("\n2. Testing negative quantity...")
    result = client.reserve_inventory([{'id': 1, 'quantity': -5}], 'ordered_item')
    if result['status_code'] == 422 or result['status_code'] == 400:
        logger.info(f"✅ Correctly rejected negative quantity (HTTP {result['status_code']})")
    else:
        logger.warning(f"⚠️ Unexpected status code: {result['status_code']}")
    
    # Test 3: Invalid item_type
    logger.info("\n3. Testing invalid item_type...")
    result = client.reserve_inventory([{'id': 1, 'quantity': 5}], 'invalid_type')
    if result['status_code'] == 422 or result['status_code'] == 400:
        logger.info(f"✅ Correctly rejected invalid item_type (HTTP {result['status_code']})")
    else:
        logger.warning(f"⚠️ Unexpected status code: {result['status_code']}")
    
    return result


# ==================== MAIN TEST RUNNER ====================

def run_all_tests():
    """Run all inventory endpoint tests"""
    logger.info("\n" + "🚀"*30)
    logger.info("INVENTORY ENDPOINT TEST SUITE")
    logger.info("🚀"*30)
    
    client = InventoryTestClient()
    results = {}
    
    # 1. Health Check
    results['health'] = test_health_check(client)
    if results['health']['status_code'] != 200:
        logger.error("❌ Health check failed. Stopping tests.")
        return results
    
    # 2. Query Tests
    results['get_stock'] = test_get_stock_status(client)
    results['bulk_stock'] = test_bulk_stock_status(client)
    results['available'] = test_get_available_quantity(client)
    results['summary'] = test_get_inventory_summary(client)
    
    # 3. Reservation Tests
    results['reserve_ordered'] = test_reserve_ordered_items(client)
    results['reserve_consumptions'] = test_reserve_consumptions(client)
    results['check_reserve'] = test_check_and_reserve(client)
    
    # 4. Confirmation Tests
    results['confirm'] = test_confirm_ordered_items(client)
    
    # 5. Release Tests
    results['release'] = test_release_ordered_items(client)
    
    # 6. Bulk Operations
    results['bulk'] = test_bulk_operations(client)
    
    # 7. Edge Cases
    results['insufficient'] = test_insufficient_stock_scenario(client)
    results['invalid'] = test_invalid_scenarios(client)
    
    # 8. Summary
    logger.info("\n" + "="*60)
    logger.info("TEST SUMMARY")
    logger.info("="*60)
    
    success_count = sum(1 for r in results.values() if isinstance(r, dict) and r.get('status_code') == 200)
    total_count = len([r for r in results.values() if isinstance(r, dict)])
    
    logger.info(f"Tests passed: {success_count}/{total_count}")
    
    if success_count == total_count:
        logger.info("✅ All tests passed!")
    else:
        logger.warning(f"⚠️ Some tests failed: {total_count - success_count} failures")
    
    return results


def test_get_available_quantity(client: InventoryTestClient):
    """Test getting available quantity"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Get Available Quantity")
    logger.info("="*60)
    
    product_id = 1
    result = client.get_available_quantity(product_id)
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Product {product_id}:")
        logger.info(f"   Available quantity: {data.get('available_quantity')}")
    else:
        logger.error(f"❌ Failed to get available quantity: {result.get('error', 'Unknown error')}")
    
    return result


def test_get_inventory_summary(client: InventoryTestClient):
    """Test getting inventory summary"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Get Inventory Summary")
    logger.info("="*60)
    
    product_id = 1
    result = client.get_inventory_summary(product_id)
    
    if result['status_code'] == 200:
        data = result['data']
        logger.info(f"✅ Product {product_id} summary:")
        logger.info(f"   ID: {data.get('id')}")
        logger.info(f"   Stock: {data.get('stock_quantity')}")
        logger.info(f"   Reserved: {data.get('reserved_quantity')}")
        logger.info(f"   Available: {data.get('available_quantity')}")
        logger.info(f"   Version: {data.get('version')}")
    else:
        logger.error(f"❌ Failed to get inventory summary: {result.get('error', 'Unknown error')}")
    
    return result


# ==================== RUN TESTS ====================

if __name__ == "__main__":
    try:
        # Check if server is running
        import requests
        try:
            health_check = requests.get(f"{BASE_URL}/health")
            logger.info(f"✅ Server is running: {health_check.status_code}")
        except:
            logger.warning("⚠️  Server health check failed. Make sure the server is running.")
            logger.info("Continuing with tests anyway...")
        
        # Run all tests
        results = run_all_tests()
        
        logger.info("\n✅ All tests completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Tests interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()



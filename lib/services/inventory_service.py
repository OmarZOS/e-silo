# lib/services/inventory_service.py

from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
import logging

from lib.repositories.inventory_repository import InventoryRepository
from lib.repositories.ordered_item_repository import OrderedItemRepository
from lib.repositories.product_consumption_repository import ProductConsumptionRepository
from core.transaction import transactional
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_409_CONFLICT

logger = logging.getLogger(__name__)


class InventoryService:
    """
    High-performance inventory service using atomic updates.
    
    Key principles:
    1. All inventory operations are single SQL UPDATE statements
    2. No SELECT ... FOR UPDATE (contention-heavy)
    3. Aggregate reserved_quantity maintained in Product table
    4. OrderedItem/ProductConsumption for detailed audit trail
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.inventory_repo = InventoryRepository(session)
        self.ordered_item_repo = OrderedItemRepository(session)
        self.consumption_repo = ProductConsumptionRepository(session)
    
    # ==================== RESERVATION OPERATIONS ====================
    
    @transactional
    def reserve_for_ordered_items(self, 
                                 items: List[Dict[str, int]],
                                 session: Session = None) -> Dict[str, Any]:
        """
        Reserve inventory for ordered items.
        
        Args:
            items: List of dicts with 'ordered_item_id' and 'quantity'
            session: SQLAlchemy session (injected by transactional decorator)
            
        Returns:
            Dict with reservation results
        """
        if session is None:
            session = self.session
        
        success_items = []
        failed_items = []
        
        # First, get all ordered items to know which products to reserve
        ordered_item_ids = [item['ordered_item_id'] for item in items]
        ordered_items = []
        
        for item_id in ordered_item_ids:
            ordered_item = self.ordered_item_repo.get_by_id(item_id)
            if ordered_item:
                ordered_items.append(ordered_item)
        
        # Map ordered_item_id -> product_id
        product_map = {
            item.id_ordered_item: item.ordered_product_id
            for item in ordered_items
        }
        
        # Prepare inventory reservation items
        inventory_items = []
        for item in items:
            ordered_item_id = item['ordered_item_id']
            quantity = item['quantity']
            
            product_id = product_map.get(ordered_item_id)
            if not product_id:
                failed_items.append({
                    'ordered_item_id': ordered_item_id,
                    'reason': 'Ordered item not found or has no product'
                })
                continue
            
            inventory_items.append({
                'product_id': product_id,
                'quantity': quantity,
                'ordered_item_id': ordered_item_id
            })
        
        # Execute atomic reservations
        results = {}
        for inv_item in inventory_items:
            success = self.inventory_repo.reserve_inventory(
                inv_item['product_id'],
                inv_item['quantity']
            )
            
            if success:
                # Update ordered_item to reflect reserved quantity
                ordered_item = self.ordered_item_repo.get_by_id(inv_item['ordered_item_id'])
                if ordered_item:
                    # Store reserved quantity in ordered_item for audit
                    ordered_item.ordered_reserved_quantity = inv_item['quantity']
                    ordered_item.ordered_item_delivery_status = 'processing'
                    session.add(ordered_item)
                
                success_items.append({
                    'ordered_item_id': inv_item['ordered_item_id'],
                    'product_id': inv_item['product_id'],
                    'reserved_quantity': inv_item['quantity']
                })
                results[inv_item['ordered_item_id']] = True
            else:
                failed_items.append({
                    'ordered_item_id': inv_item['ordered_item_id'],
                    'product_id': inv_item['product_id'],
                    'reason': 'Insufficient stock'
                })
                results[inv_item['ordered_item_id']] = False
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items,
            'results': results
        }
    
    @transactional
    def reserve_for_consumptions(self,
                                items: List[Dict[str, int]],
                                session: Session = None) -> Dict[str, Any]:
        """
        Reserve inventory for product consumptions (services).
        
        Args:
            items: List of dicts with 'consumption_id' and 'quantity'
            session: SQLAlchemy session (injected by transactional decorator)
            
        Returns:
            Dict with reservation results
        """
        if session is None:
            session = self.session
        
        success_items = []
        failed_items = []
        
        # Get all consumptions
        consumption_ids = [item['consumption_id'] for item in items]
        consumptions = []
        
        for consumption_id in consumption_ids:
            consumption = self.consumption_repo.get_by_id(consumption_id)
            if consumption:
                consumptions.append(consumption)
        
        # Map consumption_id -> product_id
        product_map = {
            c.id_product_consumption: c.consumed_product_id
            for c in consumptions
        }
        
        # Prepare inventory reservation items
        inventory_items = []
        for item in items:
            consumption_id = item['consumption_id']
            quantity = item['quantity']
            
            product_id = product_map.get(consumption_id)
            if not product_id:
                failed_items.append({
                    'consumption_id': consumption_id,
                    'reason': 'Consumption not found or has no product'
                })
                continue
            
            inventory_items.append({
                'product_id': product_id,
                'quantity': quantity,
                'consumption_id': consumption_id
            })
        
        # Execute atomic reservations
        results = {}
        for inv_item in inventory_items:
            success = self.inventory_repo.reserve_inventory(
                inv_item['product_id'],
                inv_item['quantity']
            )
            
            if success:
                # Update consumption record
                consumption = self.consumption_repo.get_by_id(inv_item['consumption_id'])
                if consumption:
                    consumption.product_reserved_quantity = inv_item['quantity']
                    session.add(consumption)
                
                success_items.append({
                    'consumption_id': inv_item['consumption_id'],
                    'product_id': inv_item['product_id'],
                    'reserved_quantity': inv_item['quantity']
                })
                results[inv_item['consumption_id']] = True
            else:
                failed_items.append({
                    'consumption_id': inv_item['consumption_id'],
                    'product_id': inv_item['product_id'],
                    'reason': 'Insufficient stock'
                })
                results[inv_item['consumption_id']] = False
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items,
            'results': results
        }
    
    # ==================== CONFIRMATION (DEDUCTION) OPERATIONS ====================
    
    @transactional
    def confirm_ordered_items(self,
                             items: List[Dict[str, int]],
                             session: Session = None) -> Dict[str, Any]:
        """
        Confirm reservations for ordered items (move from reserved to stock).
        Called when payment succeeds.
        """
        if session is None:
            session = self.session
        
        success_items = []
        failed_items = []
        
        # Get ordered items
        ordered_item_ids = [item['ordered_item_id'] for item in items]
        ordered_items = []
        
        for item_id in ordered_item_ids:
            ordered_item = self.ordered_item_repo.get_by_id(item_id)
            if ordered_item:
                ordered_items.append(ordered_item)
        
        # Map ordered_item_id -> product_id
        product_map = {
            item.id_ordered_item: item.ordered_product_id
            for item in ordered_items
        }
        
        for item in items:
            ordered_item_id = item['ordered_item_id']
            quantity = item['quantity']
            
            product_id = product_map.get(ordered_item_id)
            if not product_id:
                failed_items.append({
                    'ordered_item_id': ordered_item_id,
                    'reason': 'Ordered item not found'
                })
                continue
            
            # Confirm reservation (atomic update)
            success = self.inventory_repo.confirm_reservation(product_id, quantity)
            
            if success:
                # Update ordered item status
                ordered_item = self.ordered_item_repo.get_by_id(ordered_item_id)
                if ordered_item:
                    ordered_item.ordered_item_delivery_status = 'delivered'
                    session.add(ordered_item)
                
                success_items.append({
                    'ordered_item_id': ordered_item_id,
                    'product_id': product_id,
                    'confirmed_quantity': quantity
                })
            else:
                failed_items.append({
                    'ordered_item_id': ordered_item_id,
                    'product_id': product_id,
                    'reason': 'Failed to confirm reservation'
                })
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    @transactional
    def confirm_consumptions(self,
                            items: List[Dict[str, int]],
                            session: Session = None) -> Dict[str, Any]:
        """
        Confirm reservations for consumptions (move from reserved to stock).
        Called when service is completed.
        """
        if session is None:
            session = self.session
        
        success_items = []
        failed_items = []
        
        # Get consumptions
        consumption_ids = [item['consumption_id'] for item in items]
        consumptions = []
        
        for consumption_id in consumption_ids:
            consumption = self.consumption_repo.get_by_id(consumption_id)
            if consumption:
                consumptions.append(consumption)
        
        # Map consumption_id -> product_id
        product_map = {
            c.id_product_consumption: c.consumed_product_id
            for c in consumptions
        }
        
        for item in items:
            consumption_id = item['consumption_id']
            quantity = item['quantity']
            
            product_id = product_map.get(consumption_id)
            if not product_id:
                failed_items.append({
                    'consumption_id': consumption_id,
                    'reason': 'Consumption not found'
                })
                continue
            
            success = self.inventory_repo.confirm_reservation(product_id, quantity)
            
            if success:
                consumption = self.consumption_repo.get_by_id(consumption_id)
                if consumption:
                    consumption.product_reserved_quantity = 0
                    session.add(consumption)
                
                success_items.append({
                    'consumption_id': consumption_id,
                    'product_id': product_id,
                    'confirmed_quantity': quantity
                })
            else:
                failed_items.append({
                    'consumption_id': consumption_id,
                    'product_id': product_id,
                    'reason': 'Failed to confirm reservation'
                })
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    # ==================== RELEASE OPERATIONS ====================
    
    @transactional
    def release_ordered_items(self,
                             items: List[Dict[str, int]],
                             session: Session = None) -> Dict[str, Any]:
        """
        Release reservations for ordered items (when order is cancelled).
        """
        if session is None:
            session = self.session
        
        success_items = []
        failed_items = []
        
        # Get ordered items
        ordered_item_ids = [item['ordered_item_id'] for item in items]
        ordered_items = []
        
        for item_id in ordered_item_ids:
            ordered_item = self.ordered_item_repo.get_by_id(item_id)
            if ordered_item:
                ordered_items.append(ordered_item)
        
        # Map ordered_item_id -> product_id
        product_map = {
            item.id_ordered_item: item.ordered_product_id
            for item in ordered_items
        }
        
        for item in items:
            ordered_item_id = item['ordered_item_id']
            quantity = item['quantity']
            
            product_id = product_map.get(ordered_item_id)
            if not product_id:
                failed_items.append({
                    'ordered_item_id': ordered_item_id,
                    'reason': 'Ordered item not found'
                })
                continue
            
            success = self.inventory_repo.release_reservation(product_id, quantity)
            
            if success:
                ordered_item = self.ordered_item_repo.get_by_id(ordered_item_id)
                if ordered_item:
                    ordered_item.ordered_item_delivery_status = 'cancelled'
                    ordered_item.ordered_reserved_quantity = 0
                    session.add(ordered_item)
                
                success_items.append({
                    'ordered_item_id': ordered_item_id,
                    'product_id': product_id,
                    'released_quantity': quantity
                })
            else:
                failed_items.append({
                    'ordered_item_id': ordered_item_id,
                    'product_id': product_id,
                    'reason': 'Failed to release reservation'
                })
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    @transactional
    def release_consumptions(self,
                            items: List[Dict[str, int]],
                            session: Session = None) -> Dict[str, Any]:
        """
        Release reservations for consumptions (when service is cancelled).
        """
        if session is None:
            session = self.session
        
        success_items = []
        failed_items = []
        
        # Get consumptions
        consumption_ids = [item['consumption_id'] for item in items]
        consumptions = []
        
        for consumption_id in consumption_ids:
            consumption = self.consumption_repo.get_by_id(consumption_id)
            if consumption:
                consumptions.append(consumption)
        
        # Map consumption_id -> product_id
        product_map = {
            c.id_product_consumption: c.consumed_product_id
            for c in consumptions
        }
        
        for item in items:
            consumption_id = item['consumption_id']
            quantity = item['quantity']
            
            product_id = product_map.get(consumption_id)
            if not product_id:
                failed_items.append({
                    'consumption_id': consumption_id,
                    'reason': 'Consumption not found'
                })
                continue
            
            success = self.inventory_repo.release_reservation(product_id, quantity)
            
            if success:
                consumption = self.consumption_repo.get_by_id(consumption_id)
                if consumption:
                    consumption.product_reserved_quantity = 0
                    session.add(consumption)
                
                success_items.append({
                    'consumption_id': consumption_id,
                    'product_id': product_id,
                    'released_quantity': quantity
                })
            else:
                failed_items.append({
                    'consumption_id': consumption_id,
                    'product_id': product_id,
                    'reason': 'Failed to release reservation'
                })
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    # ==================== BATCH OPERATIONS ====================
    
    def check_and_reserve(self, items: List[Dict[str, int]], item_type: str) -> Dict[str, Any]:
        """
        Check availability and reserve in one go.
        Returns detailed results for each item.
        """
        results = {
            'success': True,
            'items': []
        }
        
        for item in items:
            item_result = {
                'id': item['id'],
                'quantity': item['quantity'],
                'success': False,
                'reason': None
            }
            
            # Get product_id
            product_id = None
            if item_type == 'ordered_item':
                ordered_item = self.ordered_item_repo.get_by_id(item['id'])
                if ordered_item:
                    product_id = ordered_item.ordered_product_id
                    item_result['product_id'] = product_id
                else:
                    item_result['reason'] = 'Ordered item not found'
                    results['items'].append(item_result)
                    results['success'] = False
                    continue
            elif item_type == 'consumption':
                consumption = self.consumption_repo.get_by_id(item['id'])
                if consumption:
                    product_id = consumption.consumed_product_id
                    item_result['product_id'] = product_id
                else:
                    item_result['reason'] = 'Consumption not found'
                    results['items'].append(item_result)
                    results['success'] = False
                    continue
            else:
                raise ValueError(f"Invalid item_type: {item_type}")
            
            if not product_id:
                item_result['reason'] = 'No product associated'
                results['items'].append(item_result)
                results['success'] = False
                continue
            
            # Execute atomic reservation
            success = self.inventory_repo.reserve_inventory(product_id, item['quantity'])
            
            if success:
                item_result['success'] = True
                if item_type == 'ordered_item':
                    ordered_item = self.ordered_item_repo.get_by_id(item['id'])
                    if ordered_item:
                        ordered_item.ordered_item_delivery_status = 'processing'
                        self.session.add(ordered_item)
                else:
                    consumption = self.consumption_repo.get_by_id(item['id'])
                    if consumption:
                        consumption.product_reserved_quantity = item['quantity']
                        self.session.add(consumption)
            else:
                item_result['reason'] = 'Insufficient stock'
                results['success'] = False
            
            results['items'].append(item_result)
        
        self.session.flush()
        return results
    
    # ==================== QUERY OPERATIONS ====================
    
    def get_available_quantity(self, product_id: int) -> int:
        """Get available quantity for a product"""
        return self.inventory_repo.get_available_quantity(product_id)
    
    def get_stock_status(self, product_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Get stock status for multiple products"""
        return self.inventory_repo.get_stock_status(product_ids)
    
    def get_inventory_summary(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed inventory summary"""
        return self.inventory_repo.get_inventory(product_id)
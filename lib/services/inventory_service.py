# lib/services/inventory_service.py

from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
import logging

from lib.repositories.inventory_repository import InventoryRepository
from lib.repositories.ordered_item_repository import OrderedItemRepository
from lib.repositories.product_consumption_repository import ProductConsumptionRepository
from core.transaction import transactional, handle_db_errors
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_409_CONFLICT, HTTP_404_NOT_FOUND

logger = logging.getLogger(__name__)


class InventoryService:
    """
    High-performance inventory service using atomic updates.
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.inventory_repo = InventoryRepository(session)
        self.ordered_item_repo = OrderedItemRepository(session)
        self.consumption_repo = ProductConsumptionRepository(session)
    
    # ==================== RESERVATION OPERATIONS ====================
    
    @handle_db_errors
    def reserve_for_ordered_items(self, items: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        Reserve inventory for ordered items.
        Raises 404 if any ordered item is not found.
        """
        success_items = []
        failed_items = []
        not_found_items = []
        
        # Get all ordered items to know which products to reserve
        ordered_item_ids = [item['ordered_item_id'] for item in items]
        ordered_items = []
        
        for item_id in ordered_item_ids:
            ordered_item = self.ordered_item_repo.get_by_id(item_id)
            if ordered_item:
                ordered_items.append(ordered_item)
            else:
                not_found_items.append(item_id)
        
        # If any items not found, raise 404
        if not_found_items:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Ordered items not found: {', '.join(map(str, not_found_items))}"
            )
        
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
                    'reason': 'Ordered item has no product'
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
                    ordered_item.reserved_quantity = inv_item['quantity']
                    ordered_item.ordered_item_delivery_status = 'processing'
                    self.session.add(ordered_item)
                
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
        
        self.session.commit()
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items,
            'results': results
        }
    
    @handle_db_errors
    def reserve_for_consumptions(self, items: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        Reserve inventory for product consumptions (services).
        Raises 404 if any consumption is not found.
        """
        success_items = []
        failed_items = []
        not_found_items = []
        
        # Get all consumptions
        consumption_ids = [item['consumption_id'] for item in items]
        consumptions = []
        
        for consumption_id in consumption_ids:
            consumption = self.consumption_repo.get_by_id(consumption_id)
            if consumption:
                consumptions.append(consumption)
            else:
                not_found_items.append(consumption_id)
        
        # If any items not found, raise 404
        if not_found_items:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Consumptions not found: {', '.join(map(str, not_found_items))}"
            )
        
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
                    'reason': 'Consumption has no product'
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
                    self.session.add(consumption)
                
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
        
        self.session.commit()
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items,
            'results': results
        }
    
    # ==================== CONFIRMATION OPERATIONS ====================
    
    @handle_db_errors
    def confirm_ordered_items(self, items: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        Confirm reservations for ordered items.
        Raises 404 if any ordered item is not found.
        """
        success_items = []
        failed_items = []
        not_found_items = []
        
        # Get ordered items
        ordered_item_ids = [item['ordered_item_id'] for item in items]
        ordered_items = []
        
        for item_id in ordered_item_ids:
            ordered_item = self.ordered_item_repo.get_by_id(item_id)
            if ordered_item:
                ordered_items.append(ordered_item)
            else:
                not_found_items.append(item_id)
        
        # If any items not found, raise 404
        if not_found_items:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Ordered items not found: {', '.join(map(str, not_found_items))}"
            )
        
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
                    'reason': 'Ordered item has no product'
                })
                continue
            
            success = self.inventory_repo.confirm_reservation(product_id, quantity)
            
            if success:
                ordered_item = self.ordered_item_repo.get_by_id(ordered_item_id)
                if ordered_item:
                    ordered_item.ordered_item_delivery_status = 'delivered'
                    ordered_item.reserved_quantity = 0
                    self.session.add(ordered_item)
                
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
        
        self.session.commit()
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    @handle_db_errors
    def confirm_consumptions(self, items: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        Confirm reservations for consumptions.
        Raises 404 if any consumption is not found.
        """
        success_items = []
        failed_items = []
        not_found_items = []
        
        # Get consumptions
        consumption_ids = [item['consumption_id'] for item in items]
        consumptions = []
        
        for consumption_id in consumption_ids:
            consumption = self.consumption_repo.get_by_id(consumption_id)
            if consumption:
                consumptions.append(consumption)
            else:
                not_found_items.append(consumption_id)
        
        # If any items not found, raise 404
        if not_found_items:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Consumptions not found: {', '.join(map(str, not_found_items))}"
            )
        
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
                    'reason': 'Consumption has no product'
                })
                continue
            
            success = self.inventory_repo.confirm_reservation(product_id, quantity)
            
            if success:
                consumption = self.consumption_repo.get_by_id(consumption_id)
                if consumption:
                    consumption.product_reserved_quantity = 0
                    self.session.add(consumption)
                
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
        
        self.session.commit()
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    # ==================== RELEASE OPERATIONS ====================
    
    @handle_db_errors
    def release_ordered_items(self, items: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        Release reservations for ordered items.
        Raises 404 if any ordered item is not found.
        """
        success_items = []
        failed_items = []
        not_found_items = []
        
        # Get ordered items
        ordered_item_ids = [item['ordered_item_id'] for item in items]
        ordered_items = []
        
        for item_id in ordered_item_ids:
            ordered_item = self.ordered_item_repo.get_by_id(item_id)
            if ordered_item:
                ordered_items.append(ordered_item)
            else:
                not_found_items.append(item_id)
        
        # If any items not found, raise 404
        if not_found_items:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Ordered items not found: {', '.join(map(str, not_found_items))}"
            )
        
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
                    'reason': 'Ordered item has no product'
                })
                continue
            
            success = self.inventory_repo.release_reservation(product_id, quantity)
            
            if success:
                ordered_item = self.ordered_item_repo.get_by_id(ordered_item_id)
                if ordered_item:
                    ordered_item.ordered_item_delivery_status = 'cancelled'
                    ordered_item.reserved_quantity = 0
                    self.session.add(ordered_item)
                
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
        
        self.session.commit()
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    @handle_db_errors
    def release_consumptions(self, items: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        Release reservations for consumptions.
        Raises 404 if any consumption is not found.
        """
        success_items = []
        failed_items = []
        not_found_items = []
        
        # Get consumptions
        consumption_ids = [item['consumption_id'] for item in items]
        consumptions = []
        
        for consumption_id in consumption_ids:
            consumption = self.consumption_repo.get_by_id(consumption_id)
            if consumption:
                consumptions.append(consumption)
            else:
                not_found_items.append(consumption_id)
        
        # If any items not found, raise 404
        if not_found_items:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Consumptions not found: {', '.join(map(str, not_found_items))}"
            )
        
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
                    'reason': 'Consumption has no product'
                })
                continue
            
            success = self.inventory_repo.release_reservation(product_id, quantity)
            
            if success:
                consumption = self.consumption_repo.get_by_id(consumption_id)
                if consumption:
                    consumption.product_reserved_quantity = 0
                    self.session.add(consumption)
                
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
        
        self.session.commit()
        
        return {
            'success': len(failed_items) == 0,
            'success_count': len(success_items),
            'failed_count': len(failed_items),
            'success_items': success_items,
            'failed_items': failed_items
        }
    
    # ==================== BATCH OPERATIONS ====================
    
    @handle_db_errors
    def check_and_reserve(self, items: List[Dict[str, int]], item_type: str) -> Dict[str, Any]:
        """
        Check availability and reserve in one go.
        Raises 404 if any item is not found.
        """
        results = {
            'success': True,
            'items': []
        }
        
        not_found_items = []
        
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
                    not_found_items.append(item['id'])
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
                    not_found_items.append(item['id'])
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
                        ordered_item.reserved_quantity = item['quantity']
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
        
        # If any items not found, raise 404
        if not_found_items:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Items not found: {', '.join(map(str, not_found_items))}"
            )
        
        self.session.commit()
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
    
    @handle_db_errors
    def bulk_confirm_atomic(self, 
                            ordered_items: List[Dict[str, int]], 
                            consumptions: List[Dict[str, int]]) -> Dict[str, Any]:
        """
        ATOMIC bulk confirmation - ALL items must succeed or NONE will be confirmed.
        This ensures data consistency for combined product and service orders.
        """
        # Collect all items to check
        all_items = []
        ordered_item_map = {}
        consumption_map = {}
        
        # Prepare ordered items
        for item in ordered_items:
            ordered_item_id = item['ordered_item_id']
            quantity = item['quantity']
            ordered_item = self.ordered_item_repo.get_by_id(ordered_item_id)
            
            if not ordered_item:
                raise APIException(
                    status_code=HTTP_404_NOT_FOUND,
                    error_code=ErrorCode.DATA_ERROR,
                    message=f"Ordered item {ordered_item_id} not found"
                )
            
            product_id = ordered_item.ordered_product_id
            if not product_id:
                raise APIException(
                    status_code=HTTP_404_NOT_FOUND,
                    error_code=ErrorCode.DATA_ERROR,
                    message=f"Ordered item {ordered_item_id} has no product"
                )
            
            ordered_item_map[ordered_item_id] = {
                'product_id': product_id,
                'quantity': quantity,
                'ordered_item': ordered_item
            }
            all_items.append({
                'type': 'ordered_item',
                'id': ordered_item_id,
                'product_id': product_id,
                'quantity': quantity
            })
        
        # Prepare consumptions
        for item in consumptions:
            consumption_id = item['consumption_id']
            quantity = item['quantity']
            consumption = self.consumption_repo.get_by_id(consumption_id)
            
            if not consumption:
                raise APIException(
                    status_code=HTTP_404_NOT_FOUND,
                    error_code=ErrorCode.DATA_ERROR,
                    message=f"Consumption {consumption_id} not found"
                )
            
            product_id = consumption.consumed_product_id
            if not product_id:
                raise APIException(
                    status_code=HTTP_404_NOT_FOUND,
                    error_code=ErrorCode.DATA_ERROR,
                    message=f"Consumption {consumption_id} has no product"
                )
            
            consumption_map[consumption_id] = {
                'product_id': product_id,
                'quantity': quantity,
                'consumption': consumption
            }
            all_items.append({
                'type': 'consumption',
                'id': consumption_id,
                'product_id': product_id,
                'quantity': quantity
            })
        
        # If no items, return error
        if not all_items:
            raise ValueError("No items to confirm")
        
        # Start a database transaction
        try:
            # STEP 1: Verify ALL items have sufficient reserved stock
            for item in all_items:
                product_id = item['product_id']
                quantity = item['quantity']
                
                # Check if we can confirm (enough reserved stock)
                can_confirm = self.inventory_repo.check_confirmation_available(product_id, quantity)
                if not can_confirm:
                    raise APIException(
                        status_code=HTTP_409_CONFLICT,
                        error_code=ErrorCode.INSUFFICIENT_STOCK,
                        message=f"Insufficient reserved stock for product {product_id}. "
                                f"Required: {quantity}"
                    )
            
            # STEP 2: All checks passed - execute confirmations
            confirmed_ordered_items = []
            confirmed_consumptions = []
            
            # Confirm ordered items
            for ordered_item_id, data in ordered_item_map.items():
                product_id = data['product_id']
                quantity = data['quantity']
                ordered_item = data['ordered_item']
                
                success = self.inventory_repo.confirm_reservation(product_id, quantity)
                if success:
                    ordered_item.ordered_item_delivery_status = 'delivered'
                    ordered_item.reserved_quantity = 0
                    self.session.add(ordered_item)
                    
                    confirmed_ordered_items.append({
                        'ordered_item_id': ordered_item_id,
                        'product_id': product_id,
                        'confirmed_quantity': quantity
                    })
                else:
                    # This should not happen if check passed, but just in case
                    raise APIException(
                        status_code=HTTP_409_CONFLICT,
                        error_code=ErrorCode.INSUFFICIENT_STOCK,
                        message=f"Failed to confirm ordered item {ordered_item_id}"
                    )
            
            # Confirm consumptions
            for consumption_id, data in consumption_map.items():
                product_id = data['product_id']
                quantity = data['quantity']
                consumption = data['consumption']
                
                success = self.inventory_repo.confirm_reservation(product_id, quantity)
                if success:
                    consumption.product_reserved_quantity = 0
                    self.session.add(consumption)
                    
                    confirmed_consumptions.append({
                        'consumption_id': consumption_id,
                        'product_id': product_id,
                        'confirmed_quantity': quantity
                    })
                else:
                    # This should not happen if check passed, but just in case
                    raise APIException(
                        status_code=HTTP_409_CONFLICT,
                        error_code=ErrorCode.INSUFFICIENT_STOCK,
                        message=f"Failed to confirm consumption {consumption_id}"
                    )
            
            # Commit all changes atomically
            self.session.commit()
            
            return {
                'ordered_items': {
                    'success': True,
                    'success_count': len(confirmed_ordered_items),
                    'failed_count': 0,
                    'success_items': confirmed_ordered_items,
                    'failed_items': []
                },
                'consumptions': {
                    'success': True,
                    'success_count': len(confirmed_consumptions),
                    'failed_count': 0,
                    'success_items': confirmed_consumptions,
                    'failed_items': []
                },
                'overall_success': True,
                'errors': []
            }
            
        except Exception as e:
            # Rollback everything
            self.session.rollback()
            logger.error(f"Bulk confirmation failed: {e}")
            raise
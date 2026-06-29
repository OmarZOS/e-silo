# lib/repositories/ordered_item_repository.py

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from datetime import datetime
import logging

from core.models import OrderedItem, Product, PlacedOrder
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

logger = logging.getLogger(__name__)


class OrderedItemRepository:
    """Repository for OrderedItem model operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_by_id(self, ordered_item_id: int, include_relationships: bool = False) -> Optional[OrderedItem]:
        """Get ordered item by ID"""
        query = self.session.query(OrderedItem)
        
        if include_relationships:
            query = query.options(
                joinedload(OrderedItem.ordered_product),
                joinedload(OrderedItem.placed_order),
                joinedload(OrderedItem.cart)
            )
        
        return query.filter(OrderedItem.id_ordered_item == ordered_item_id).first()
    
    def get_by_order(self, order_id: int) -> List[OrderedItem]:
        """Get all ordered items for a placed order"""
        return self.session.query(OrderedItem).filter(
            OrderedItem.order_ref == order_id
        ).options(
            joinedload(OrderedItem.ordered_product)
        ).all()
    
    def get_by_cart(self, cart_id: int) -> List[OrderedItem]:
        """Get all ordered items for a cart"""
        return self.session.query(OrderedItem).filter(
            OrderedItem.ordered_item_cart_ref == cart_id
        ).options(
            joinedload(OrderedItem.ordered_product)
        ).all()
    
    def get_by_product(self, product_id: int, 
                       status: Optional[str] = None,
                       limit: int = 100) -> List[OrderedItem]:
        """Get ordered items by product"""
        query = self.session.query(OrderedItem).filter(
            OrderedItem.ordered_product_id == product_id
        )
        
        if status:
            query = query.filter(OrderedItem.ordered_item_delivery_status == status)
        
        return query.limit(limit).all()
    
    def get_by_status(self, status: str, limit: int = 100) -> List[OrderedItem]:
        """Get ordered items by delivery status"""
        return self.session.query(OrderedItem).filter(
            OrderedItem.ordered_item_delivery_status == status
        ).options(
            joinedload(OrderedItem.ordered_product)
        ).limit(limit).all()
    
    def create_ordered_item(self, 
                           product_id: int,
                           quantity: int,
                           order_id: int,
                           cart_id: Optional[int] = None,
                           unit_price: Optional[float] = None,
                           discount: float = 0.0,
                           delivery_fee: float = 0.0) -> OrderedItem:
        """Create a new ordered item"""
        # Get product to get price if not provided
        product = self.session.query(Product).filter(
            Product.id_product == product_id
        ).first()
        
        if not product:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Product with ID {product_id} not found"
            )
        
        # Check if product has sufficient quantity
        if (product.product_quantity or 0) < quantity:
            raise APIException(
                status_code=HTTP_409_CONFLICT,
                error_code=ErrorCode.INSUFFICIENT_STOCK,
                message=f"Insufficient stock for product {product.product_name}. "
                        f"Available: {product.product_quantity}, Requested: {quantity}"
            )
        
        # Calculate unit price if not provided
        if unit_price is None:
            unit_price = float(product.product_price or 0)
        
        # Create ordered item
        ordered_item = OrderedItem(
            ordered_product_id=product_id,
            ordered_quantity=quantity,
            unit_price=unit_price,
            product_discount=discount,
            applied_vat=0.0,  # Calculate VAT as needed
            order_ref=order_id,
            ordered_item_cart_ref=cart_id,
            ordered_item_delivery_fee=delivery_fee,
            ordered_item_delivery_status='pending'
        )
        
        self.session.add(ordered_item)
        self.session.flush()
        self.session.refresh(ordered_item)
        
        logger.info(f"Created ordered item {ordered_item.id_ordered_item} for product {product_id}")
        return ordered_item
    
    def update_delivery_status(self, ordered_item_id: int, new_status: str) -> OrderedItem:
        """Update delivery status of ordered item"""
        ordered_item = self.get_by_id(ordered_item_id)
        if not ordered_item:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Ordered item with ID {ordered_item_id} not found"
            )
        
        valid_statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled', 'returned', 'partial']
        if new_status not in valid_statuses:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.VALIDATION_ERROR,
                message=f"Invalid status: {new_status}. Must be one of {valid_statuses}"
            )
        
        ordered_item.ordered_item_delivery_status = new_status
        self.session.add(ordered_item)
        self.session.flush()
        
        logger.info(f"Updated delivery status of {ordered_item_id} to {new_status}")
        return ordered_item
    
    def cancel_ordered_item(self, ordered_item_id: int) -> OrderedItem:
        """Cancel an ordered item and restore inventory"""
        ordered_item = self.get_by_id(ordered_item_id)
        if not ordered_item:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Ordered item with ID {ordered_item_id} not found"
            )
        
        # Restore product quantity
        product = self.session.query(Product).filter(
            Product.id_product == ordered_item.ordered_product_id
        ).first()
        
        if product:
            product.product_quantity = (product.product_quantity or 0) + ordered_item.ordered_quantity
            product.last_updated = datetime.utcnow()
            self.session.add(product)
            logger.info(
                f"Restored {ordered_item.ordered_quantity} units of product "
                f"{ordered_item.ordered_product_id} due to cancellation"
            )
        
        # Update ordered item status
        ordered_item.ordered_item_delivery_status = 'cancelled'
        self.session.add(ordered_item)
        self.session.flush()
        
        logger.info(f"Cancelled ordered item {ordered_item_id}")
        return ordered_item
    
    def get_order_summary(self, order_id: int) -> Dict[str, Any]:
        """Get summary of ordered items for an order"""
        items = self.get_by_order(order_id)
        
        if not items:
            return {
                'order_id': order_id,
                'total_items': 0,
                'total_quantity': 0,
                'total_amount': 0.0,
                'items': []
            }
        
        total_quantity = sum(item.ordered_quantity for item in items)
        total_amount = sum(
            (item.unit_price or 0) * item.ordered_quantity 
            for item in items
        )
        
        return {
            'order_id': order_id,
            'total_items': len(items),
            'total_quantity': total_quantity,
            'total_amount': total_amount,
            'items': [
                {
                    'id': item.id_ordered_item,
                    'product_id': item.ordered_product_id,
                    'product_name': item.ordered_product.product_name if item.ordered_product else None,
                    'quantity': item.ordered_quantity,
                    'unit_price': item.unit_price,
                    'total_price': (item.unit_price or 0) * item.ordered_quantity,
                    'status': item.ordered_item_delivery_status
                }
                for item in items
            ]
        }
    
    def get_delivery_status_stats(self, order_id: int) -> Dict[str, int]:
        """Get delivery status statistics for an order"""
        items = self.get_by_order(order_id)
        
        stats = {}
        for item in items:
            status = item.ordered_item_delivery_status or 'pending'
            stats[status] = stats.get(status, 0) + 1
        
        return stats
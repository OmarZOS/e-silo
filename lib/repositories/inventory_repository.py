# lib/repositories/inventory_repository.py

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text, update
import logging

from core.models import Product
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_409_CONFLICT, HTTP_404_NOT_FOUND

logger = logging.getLogger(__name__)


class InventoryRepository:
    """
    Repository for inventory operations using atomic updates.
    All operations are single SQL statements for maximum performance.
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_inventory(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Get inventory state for a product"""
        product = self.session.query(Product).filter(
            Product.id_product == product_id
        ).first()
        
        if not product:
            return None
        
        return {
            'id': product.id_product,
            'stock_quantity': product.product_quantity or 0,
            'reserved_quantity': product.product_reserved_quantity or 0,
            'available_quantity': (product.product_quantity or 0) - (product.product_reserved_quantity or 0),
        }
    
    def reserve_inventory(self, product_id: int, quantity: int) -> bool:
        """
        Atomically reserve inventory.
        
        Returns:
            True if reservation succeeded, False if insufficient stock
        
        SQL:
            UPDATE product
            SET 
                product_reserved_quantity = product_reserved_quantity + :qty,
            WHERE 
                id_product = :id
                AND (product_quantity - product_reserved_quantity) >= :qty
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        # Single atomic update
        result = self.session.execute(
            text("""
                UPDATE product
                SET 
                    product_reserved_quantity = product_reserved_quantity + :qty,
                    last_updated = NOW()
                WHERE 
                    id_product = :id
                    AND (product_quantity - product_reserved_quantity) >= :qty
            """),
            {
                'id': product_id,
                'qty': quantity
            }
        )
        
        affected_rows = result.rowcount
        
        if affected_rows == 1:
            logger.info(f"Reserved {quantity} units for product {product_id}")
            return True
        else:
            logger.warning(f"Failed to reserve {quantity} units for product {product_id} - insufficient stock")
            return False
    
    def confirm_reservation(self, product_id: int, quantity: int) -> bool:
        """
        Confirm reservation (move from reserved to stock).
        Used when payment succeeds or order is completed.
        
        SQL:
            UPDATE product
            SET 
                product_quantity = product_quantity - :qty,
                product_reserved_quantity = product_reserved_quantity - :qty,
            WHERE 
                id_product = :id
                AND product_reserved_quantity >= :qty
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        result = self.session.execute(
            text("""
                UPDATE product
                SET 
                    product_quantity = product_quantity - :qty,
                    product_reserved_quantity = product_reserved_quantity - :qty,
                    last_updated = NOW()
                WHERE 
                    id_product = :id
                    AND product_reserved_quantity >= :qty
            """),
            {
                'id': product_id,
                'qty': quantity
            }
        )
        
        affected_rows = result.rowcount
        
        if affected_rows == 1:
            logger.info(f"Confirmed reservation for {quantity} units of product {product_id}")
            return True
        else:
            logger.error(f"Failed to confirm reservation for product {product_id} - reserved quantity insufficient")
            return False
    
    def release_reservation(self, product_id: int, quantity: int) -> bool:
        """
        Release reserved inventory (when order is cancelled or fails).
        
        SQL:
            UPDATE product
            SET 
                product_reserved_quantity = product_reserved_quantity - :qty,
            WHERE 
                id_product = :id
                AND product_reserved_quantity >= :qty
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        result = self.session.execute(
            text("""
                UPDATE product
                SET 
                    product_reserved_quantity = product_reserved_quantity - :qty,
                    last_updated = NOW()
                WHERE 
                    id_product = :id
                    AND product_reserved_quantity >= :qty
            """),
            {
                'id': product_id,
                'qty': quantity
            }
        )
        
        affected_rows = result.rowcount
        
        if affected_rows == 1:
            logger.info(f"Released {quantity} units for product {product_id}")
            return True
        else:
            logger.warning(f"Failed to release {quantity} units for product {product_id} - reserved quantity insufficient")
            return False
    
    def bulk_reserve_inventory(self, items: List[Dict[str, int]]) -> Dict[int, bool]:
        """
        Bulk reserve inventory for multiple products.
        Each reservation is atomic but executed sequentially.
        
        Args:
            items: List of dicts with 'product_id' and 'quantity'
            
        Returns:
            Dict of product_id -> success (bool)
        """
        results = {}
        
        for item in items:
            product_id = item['product_id']
            quantity = item['quantity']
            results[product_id] = self.reserve_inventory(product_id, quantity)
        
        return results
    
    def bulk_confirm_reservations(self, items: List[Dict[str, int]]) -> Dict[int, bool]:
        """Bulk confirm reservations"""
        results = {}
        
        for item in items:
            product_id = item['product_id']
            quantity = item['quantity']
            results[product_id] = self.confirm_reservation(product_id, quantity)
        
        return results
    
    def bulk_release_reservations(self, items: List[Dict[str, int]]) -> Dict[int, bool]:
        """Bulk release reservations"""
        results = {}
        
        for item in items:
            product_id = item['product_id']
            quantity = item['quantity']
            results[product_id] = self.release_reservation(product_id, quantity)
        
        return results
    
    def get_available_quantity(self, product_id: int) -> int:
        """Get available quantity for a product"""
        product = self.session.query(Product).filter(
            Product.id_product == product_id
        ).first()
        
        if not product:
            return 0
        
        return (product.product_quantity or 0) - (product.product_reserved_quantity or 0)
    
    def get_stock_status(self, product_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Get stock status for multiple products"""
        products = self.session.query(Product).filter(
            Product.id_product.in_(product_ids)
        ).all()
        
        status = {}
        for product in products:
            status[product.id_product] = {
                'stock': product.product_quantity or 0,
                'reserved': product.product_reserved_quantity or 0,
                'available': (product.product_quantity or 0) - (product.product_reserved_quantity or 0),
            }
        
        return status
    
    def reset_inventory(self, product_id: int, stock_quantity: int) -> bool:
        """
        Reset inventory (admin function).
        Sets stock and resets reserved to 0.
        """
        result = self.session.execute(
            text("""
                UPDATE product
                SET 
                    product_quantity = :stock,
                    product_reserved_quantity = 0,
                    last_updated = NOW()
                WHERE 
                    id_product = :id
            """),
            {
                'id': product_id,
                'stock': stock_quantity
            }
        )
        
        affected_rows = result.rowcount
        return affected_rows == 1
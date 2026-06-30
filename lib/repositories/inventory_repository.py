# lib/repositories/inventory_repository.py

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from core.models import Product
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_409_CONFLICT, HTTP_404_NOT_FOUND

logger = logging.getLogger(__name__)


class InventoryRepository:
    """
    Repository for inventory operations using atomic updates.
    No transaction decorators here - transaction is handled by the service layer.
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
            'version': getattr(product, 'product_version', 0)
        }
    
    def reserve_inventory(self, product_id: int, quantity: int) -> bool:
        """
        Atomically reserve inventory.
        
        Returns:
            True if reservation succeeded, False if insufficient stock
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
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
            logger.error(f"Failed to confirm reservation for product {product_id}")
            return False
    
    def release_reservation(self, product_id: int, quantity: int) -> bool:
        """
        Release reserved inventory.
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
            logger.warning(f"Failed to release {quantity} units for product {product_id}")
            return False
    
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
                'version': getattr(product, 'product_version', 0)
            }
        
        return status
    
    def check_confirmation_available(self, product_id: int, quantity: int) -> bool:
        """
        Check if there is enough reserved quantity to confirm.
        Used for atomic bulk confirmations.
        """
        result = self.session.execute(
            text("""
                SELECT COUNT(*) 
                FROM product 
                WHERE id_product = :id 
                AND product_reserved_quantity >= :qty
            """),
            {
                'id': product_id,
                'qty': quantity
            }
        )
        
        count = result.scalar()
        return count == 1
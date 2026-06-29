# lib/repositories/product_repository.py

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from datetime import datetime
import logging

from core.models import Product
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

logger = logging.getLogger(__name__)


class ProductRepository:
    """Repository for Product model operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_by_id(self, product_id: int, include_relationships: bool = False) -> Optional[Product]:
        """Get product by ID"""
        query = self.session.query(Product)
        
        if include_relationships:
            query = query.options(
                joinedload(Product.product_provider),
                joinedload(Product.product_category),
                joinedload(Product.app_user)
            )
        
        return query.filter(Product.id_product == product_id).first()
    
    def get_by_provider(self, provider_id: int, 
                        include_inactive: bool = False,
                        limit: int = 100,
                        offset: int = 0) -> List[Product]:
        """Get products by provider"""
        query = self.session.query(Product).filter(
            Product.product_provider_id == provider_id
        )
        
        if not include_inactive:
            query = query.filter(Product.product_visibility == 'VISIBLE')
        
        return query.offset(offset).limit(limit).all()
    
    def get_by_category(self, category_id: int, 
                        provider_id: Optional[int] = None,
                        limit: int = 100,
                        offset: int = 0) -> List[Product]:
        """Get products by category, optionally filtered by provider"""
        query = self.session.query(Product).filter(
            Product.product_category_id == category_id,
            Product.product_visibility == 'VISIBLE'
        )
        
        if provider_id:
            query = query.filter(Product.product_provider_id == provider_id)
        
        return query.offset(offset).limit(limit).all()
    
    def get_by_barcode(self, barcode: str, provider_id: Optional[int] = None) -> Optional[Product]:
        """Get product by barcode"""
        query = self.session.query(Product).filter(
            Product.product_barcode == barcode
        )
        
        if provider_id:
            query = query.filter(Product.product_provider_id == provider_id)
        
        return query.first()
    
    def get_products_with_low_stock(self, provider_id: int, 
                                    threshold: int = 10) -> List[Product]:
        """Get products with stock below threshold"""
        return self.session.query(Product).filter(
            Product.product_provider_id == provider_id,
            Product.product_quantity <= threshold,
            Product.product_visibility == 'VISIBLE'
        ).all()
    
    def get_products_with_reserved_stock(self, provider_id: int) -> List[Product]:
        """Get products with reserved stock"""
        return self.session.query(Product).filter(
            Product.product_provider_id == provider_id,
            Product.product_reserved_quantity > 0,
            Product.product_visibility == 'VISIBLE'
        ).all()
    
    def update_quantity(self, product_id: int, quantity_change: int) -> Product:
        """
        Update product quantity (can be positive or negative)
        Raises exception if insufficient stock
        """
        product = self.get_by_id(product_id)
        if not product:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Product with ID {product_id} not found"
            )
        
        new_quantity = (product.product_quantity or 0) + quantity_change
        
        if new_quantity < 0:
            raise APIException(
                status_code=HTTP_409_CONFLICT,
                error_code=ErrorCode.INSUFFICIENT_STOCK,
                message=f"Insufficient stock for product {product.product_name}. "
                        f"Available: {product.product_quantity}, Requested: {-quantity_change}"
            )
        
        product.product_quantity = new_quantity
        product.last_updated = datetime.utcnow()
        self.session.add(product)
        self.session.flush()
        
        logger.info(f"Updated product {product_id} quantity to {new_quantity}")
        return product
    
    def reserve_quantity(self, product_id: int, quantity: int) -> Product:
        """Reserve quantity for pending orders"""
        product = self.get_by_id(product_id)
        if not product:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Product with ID {product_id} not found"
            )
        
        available = (product.product_quantity or 0) - (product.product_reserved_quantity or 0)
        
        if available < quantity:
            raise APIException(
                status_code=HTTP_409_CONFLICT,
                error_code=ErrorCode.INSUFFICIENT_STOCK,
                message=f"Insufficient available stock for product {product.product_name}. "
                        f"Available: {available}, Requested: {quantity}"
            )
        
        product.product_reserved_quantity = (product.product_reserved_quantity or 0) + quantity
        product.last_updated = datetime.utcnow()
        self.session.add(product)
        self.session.flush()
        
        logger.info(f"Reserved {quantity} units for product {product_id}")
        return product
    
    def release_reserved_quantity(self, product_id: int, quantity: int) -> Product:
        """Release reserved quantity (when order is cancelled)"""
        product = self.get_by_id(product_id)
        if not product:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Product with ID {product_id} not found"
            )
        
        current_reserved = product.product_reserved_quantity or 0
        
        if current_reserved < quantity:
            logger.warning(
                f"Attempted to release {quantity} reserved units for product {product_id}, "
                f"but only {current_reserved} are reserved"
            )
            quantity = current_reserved
        
        product.product_reserved_quantity = current_reserved - quantity
        product.last_updated = datetime.utcnow()
        self.session.add(product)
        self.session.flush()
        
        logger.info(f"Released {quantity} reserved units for product {product_id}")
        return product
    
    def deduct_reserved_quantity(self, product_id: int, quantity: int) -> Product:
        """
        Deduct from reserved quantity and actual quantity when order is confirmed
        """
        product = self.get_by_id(product_id)
        if not product:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Product with ID {product_id} not found"
            )
        
        current_reserved = product.product_reserved_quantity or 0
        
        if current_reserved < quantity:
            raise APIException(
                status_code=HTTP_409_CONFLICT,
                error_code=ErrorCode.INSUFFICIENT_STOCK,
                message=f"Insufficient reserved stock for product {product.product_name}. "
                        f"Reserved: {current_reserved}, Requested: {quantity}"
            )
        
        product.product_quantity = (product.product_quantity or 0) - quantity
        product.product_reserved_quantity = current_reserved - quantity
        product.last_updated = datetime.utcnow()
        self.session.add(product)
        self.session.flush()
        
        logger.info(
            f"Deducted {quantity} units from product {product_id}. "
            f"Remaining: {product.product_quantity}, Reserved: {product.product_reserved_quantity}"
        )
        return product
    
    def search_products(self, search_term: str, 
                        provider_id: Optional[int] = None,
                        limit: int = 50) -> List[Product]:
        """Search products by name, brand, or barcode"""
        search_pattern = f"%{search_term}%"
        
        query = self.session.query(Product).filter(
            or_(
                Product.product_name.like(search_pattern),
                Product.product_brand.like(search_pattern),
                Product.product_barcode.like(search_pattern)
            ),
            Product.product_visibility == 'VISIBLE'
        )
        
        if provider_id:
            query = query.filter(Product.product_provider_id == provider_id)
        
        return query.limit(limit).all()
    
    def get_inventory_summary(self, provider_id: int) -> Dict[str, Any]:
        """Get inventory summary for a provider"""
        products = self.session.query(Product).filter(
            Product.product_provider_id == provider_id
        ).all()
        
        total_products = len(products)
        total_quantity = sum(p.product_quantity or 0 for p in products)
        total_reserved = sum(p.product_reserved_quantity or 0 for p in products)
        total_value = sum((p.product_quantity or 0) * (p.product_price or 0) for p in products)
        
        low_stock_count = sum(1 for p in products if (p.product_quantity or 0) <= 10)
        out_of_stock_count = sum(1 for p in products if (p.product_quantity or 0) == 0)
        
        return {
            'provider_id': provider_id,
            'total_products': total_products,
            'total_quantity': total_quantity,
            'total_reserved': total_reserved,
            'available_quantity': total_quantity - total_reserved,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count
        }
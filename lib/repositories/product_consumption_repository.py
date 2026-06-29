# lib/repositories/product_consumption_repository.py

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta
import logging

from core.models import (
    ProductConsumption, Product, OrderedService, 
    ServiceResourceRequirement
)
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_404_NOT_FOUND, HTTP_409_CONFLICT
from lib.repositories.product_repository import ProductRepository

logger = logging.getLogger(__name__)


class ProductConsumptionRepository:
    """Repository for ProductConsumption model operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_by_id(self, consumption_id: int, include_relationships: bool = False) -> Optional[ProductConsumption]:
        """Get product consumption by ID"""
        query = self.session.query(ProductConsumption)
        
        if include_relationships:
            query = query.options(
                joinedload(ProductConsumption.consumed_product),
                joinedload(ProductConsumption.consuming_service),
                joinedload(ProductConsumption.service_resource_requirement)
            )
        
        return query.filter(ProductConsumption.id_product_consumption == consumption_id).first()
    
    def get_by_service(self, service_id: int) -> List[ProductConsumption]:
        """Get all consumptions for a service"""
        return self.session.query(ProductConsumption).filter(
            ProductConsumption.consuming_service_id == service_id
        ).options(
            joinedload(ProductConsumption.consumed_product),
            joinedload(ProductConsumption.service_resource_requirement)
        ).all()
    
    def get_by_product(self, product_id: int, 
                       start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None) -> List[ProductConsumption]:
        """Get consumptions by product with optional date range"""
        query = self.session.query(ProductConsumption).filter(
            ProductConsumption.consumed_product_id == product_id
        )
        
        if start_date:
            query = query.filter(
                ProductConsumption.service_resource_requirement.has(
                    ServiceResourceRequirement.service_resource_requirement_created_at >= start_date
                )
            )
        
        if end_date:
            query = query.filter(
                ProductConsumption.service_resource_requirement.has(
                    ServiceResourceRequirement.service_resource_requirement_created_at <= end_date
                )
            )
        
        return query.all()
    
    def get_by_resource_requirement(self, requirement_id: int) -> List[ProductConsumption]:
        """Get consumptions by resource requirement"""
        return self.session.query(ProductConsumption).filter(
            ProductConsumption.resource_req_ref == requirement_id
        ).all()
    
    def create_consumption(self,
                          consuming_service_id: int,
                          resource_req_ref: int,
                          consumed_product_id: int,
                          quantity: int) -> ProductConsumption:
        """
        Create a product consumption record for a service
        """
        # Verify consuming service exists
        service = self.session.query(OrderedService).filter(
            OrderedService.ordered_service_id == consuming_service_id
        ).first()
        
        if not service:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Ordered service with ID {consuming_service_id} not found"
            )
        
        # Verify resource requirement exists
        requirement = self.session.query(ServiceResourceRequirement).filter(
            ServiceResourceRequirement.service_resource_requirement_id == resource_req_ref
        ).first()
        
        if not requirement:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Resource requirement with ID {resource_req_ref} not found"
            )
        
        # Verify product exists
        product = self.session.query(Product).filter(
            Product.id_product == consumed_product_id
        ).first()
        
        if not product:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Product with ID {consumed_product_id} not found"
            )
        
        # Check if product has sufficient quantity
        if (product.product_quantity or 0) < quantity:
            raise APIException(
                status_code=HTTP_409_CONFLICT,
                error_code=ErrorCode.INSUFFICIENT_STOCK,
                message=f"Insufficient stock for product {product.product_name}. "
                        f"Available: {product.product_quantity}, Required: {quantity}"
            )
        
        # Create consumption record
        consumption = ProductConsumption(
            consuming_service_id=consuming_service_id,
            resource_req_ref=resource_req_ref,
            consumed_product_id=consumed_product_id,
            product_reserved_quantity=quantity
        )
        
        self.session.add(consumption)
        self.session.flush()
        self.session.refresh(consumption)
        
        # Update product quantity
        product.product_quantity = (product.product_quantity or 0) - quantity
        product.last_updated = datetime.utcnow()
        self.session.add(product)
        
        logger.info(
            f"Created consumption record {consumption.id_product_consumption} "
            f"for service {consuming_service_id}, "
            f"deducted {quantity} units of product {consumed_product_id}"
        )
        
        return consumption
    
    def create_bulk_consumptions(self, consumptions_data: List[Dict]) -> List[ProductConsumption]:
        """
        Create multiple product consumption records in batch
        """
        created = []
        errors = []
        
        for data in consumptions_data:
            try:
                consumption = self.create_consumption(
                    consuming_service_id=data['consuming_service_id'],
                    resource_req_ref=data['resource_req_ref'],
                    consumed_product_id=data['consumed_product_id'],
                    quantity=data['quantity']
                )
                created.append(consumption)
            except Exception as e:
                errors.append({
                    'data': data,
                    'error': str(e)
                })
        
        if errors:
            logger.error(f"Bulk consumption creation had {len(errors)} errors")
        
        return created
    
    def rollback_consumption(self, consumption_id: int) -> bool:
        """
        Rollback a consumption record (restore product quantity)
        """
        consumption = self.get_by_id(consumption_id)
        if not consumption:
            raise APIException(
                status_code=HTTP_404_NOT_FOUND,
                error_code=ErrorCode.DATA_ERROR,
                message=f"Consumption with ID {consumption_id} not found"
            )
        
        # Restore product quantity
        product = self.session.query(Product).filter(
            Product.id_product == consumption.consumed_product_id
        ).first()
        
        if product:
            product.product_quantity = (product.product_quantity or 0) + consumption.product_reserved_quantity
            product.last_updated = datetime.utcnow()
            self.session.add(product)
            logger.info(
                f"Rolled back consumption {consumption_id}, "
                f"restored {consumption.product_reserved_quantity} units of product "
                f"{consumption.consumed_product_id}"
            )
        
        # Delete consumption record
        self.session.delete(consumption)
        self.session.flush()
        
        return True
    
    def get_consumption_summary(self, service_id: int) -> Dict[str, Any]:
        """Get consumption summary for a service"""
        consumptions = self.get_by_service(service_id)
        
        if not consumptions:
            return {
                'service_id': service_id,
                'total_consumptions': 0,
                'total_quantity': 0,
                'total_cost': 0.0,
                'products': []
            }
        
        total_quantity = sum(c.product_reserved_quantity for c in consumptions)
        total_cost = 0
        
        product_summary = {}
        for consumption in consumptions:
            product = consumption.consumed_product
            if product:
                product_summary[product.id_product] = {
                    'product_id': product.id_product,
                    'product_name': product.product_name,
                    'total_quantity': product_summary.get(product.id_product, {}).get('total_quantity', 0) + consumption.product_reserved_quantity,
                    'total_cost': product_summary.get(product.id_product, {}).get('total_cost', 0) + (
                        (product.product_price or 0) * consumption.product_reserved_quantity
                    )
                }
        
        return {
            'service_id': service_id,
            'total_consumptions': len(consumptions),
            'total_quantity': total_quantity,
            'total_cost': total_cost,
            'products': list(product_summary.values())
        }
    
    def get_product_consumption_stats(self, product_id: int, 
                                      days: int = 30) -> Dict[str, Any]:
        """Get consumption statistics for a product"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        consumptions = self.session.query(ProductConsumption).filter(
            ProductConsumption.consumed_product_id == product_id,
            ProductConsumption.service_resource_requirement.has(
                ServiceResourceRequirement.service_resource_requirement_created_at >= start_date
            )
        ).all()
        
        product = self.session.query(Product).filter(
            Product.id_product == product_id
        ).first()
        
        total_consumed = sum(c.product_reserved_quantity for c in consumptions)
        avg_daily = total_consumed / days if days > 0 else 0
        
        return {
            'product_id': product_id,
            'product_name': product.product_name if product else None,
            'period_days': days,
            'total_consumed': total_consumed,
            'average_daily_consumption': avg_daily,
            'current_stock': product.product_quantity if product else 0,
            'days_of_stock_remaining': (
                (product.product_quantity or 0) / avg_daily if avg_daily > 0 else float('inf')
            ),
            'consumptions_count': len(consumptions)
        }


# Additional utility functions for inventory management

def get_inventory_health_score(provider_id: int, session: Session) -> Dict[str, Any]:
    """
    Calculate inventory health score for a provider
    """
    product_repo = ProductRepository(session)
    consumption_repo = ProductConsumptionRepository(session)
    
    products = product_repo.get_by_provider(provider_id, include_inactive=True)
    
    if not products:
        return {
            'provider_id': provider_id,
            'score': 0,
            'total_products': 0,
            'metrics': {}
        }
    
    # Calculate metrics
    total_products = len(products)
    out_of_stock = sum(1 for p in products if (p.product_quantity or 0) == 0)
    low_stock = sum(1 for p in products if 0 < (p.product_quantity or 0) <= 10)
    healthy_stock = sum(1 for p in products if (p.product_quantity or 0) > 10)
    
    # Calculate health score (0-100)
    stock_score = (healthy_stock / total_products) * 100 if total_products > 0 else 0
    availability_score = ((total_products - out_of_stock) / total_products) * 100 if total_products > 0 else 0
    
    health_score = (stock_score + availability_score) / 2
    
    return {
        'provider_id': provider_id,
        'score': round(health_score, 2),
        'total_products': total_products,
        'metrics': {
            'out_of_stock': out_of_stock,
            'low_stock': low_stock,
            'healthy_stock': healthy_stock,
            'stock_score': round(stock_score, 2),
            'availability_score': round(availability_score, 2)
        },
        'status': 'HEALTHY' if health_score > 70 else 'CAUTION' if health_score > 40 else 'CRITICAL'
    }
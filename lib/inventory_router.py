# controllers/inventory_controller.py

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
import logging

from core.database import session_scope
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT
from lib.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Inventory"])


# ==================== PYDANTIC MODELS ====================

class InventoryItem(BaseModel):
    """Single inventory item for reservation/confirmation/release"""
    id: int = Field(..., description="ID of the ordered_item or consumption")
    quantity: int = Field(..., ge=1, description="Quantity to reserve/confirm/release")
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError('Quantity must be positive')
        if v > 10000:
            raise ValueError('Quantity exceeds maximum limit of 10000')
        return v


class ReserveRequest(BaseModel):
    """Request model for reserving inventory"""
    items: List[InventoryItem] = Field(..., min_items=1, description="Items to reserve")
    item_type: str = Field(..., description="Type of items: 'ordered_item' or 'consumption'")
    
    @field_validator('item_type')
    @classmethod
    def validate_item_type(cls, v):
        if v not in ['ordered_item', 'consumption']:
            raise ValueError("item_type must be 'ordered_item' or 'consumption'")
        return v


class ConfirmRequest(BaseModel):
    """Request model for confirming inventory"""
    items: List[InventoryItem] = Field(..., min_items=1, description="Items to confirm")
    item_type: str = Field(..., description="Type of items: 'ordered_item' or 'consumption'")
    
    @field_validator('item_type')
    @classmethod
    def validate_item_type(cls, v):
        if v not in ['ordered_item', 'consumption']:
            raise ValueError("item_type must be 'ordered_item' or 'consumption'")
        return v


class ReleaseRequest(BaseModel):
    """Request model for releasing inventory"""
    items: List[InventoryItem] = Field(..., min_items=1, description="Items to release")
    item_type: str = Field(..., description="Type of items: 'ordered_item' or 'consumption'")
    
    @field_validator('item_type')
    @classmethod
    def validate_item_type(cls, v):
        if v not in ['ordered_item', 'consumption']:
            raise ValueError("item_type must be 'ordered_item' or 'consumption'")
        return v


class BulkInventoryRequest(BaseModel):
    """Request model for bulk inventory operations"""
    ordered_items: List[InventoryItem] = Field(default=[], description="Ordered items to process")
    consumptions: List[InventoryItem] = Field(default=[], description="Consumptions to process")
    
    @field_validator('ordered_items', 'consumptions')
    @classmethod
    def validate_at_least_one(cls, v, info):
        if not v and not info.data.get('consumptions') and not info.data.get('ordered_items'):
            raise ValueError('At least one of ordered_items or consumptions must be provided')
        return v


class InventoryItemResult(BaseModel):
    """Result for a single inventory item"""
    id: int
    product_id: Optional[int] = None
    quantity: int
    success: bool
    reason: Optional[str] = None


class InventoryResponse(BaseModel):
    """Response model for inventory operations"""
    success: bool
    success_count: int
    failed_count: int
    success_items: List[Dict[str, Any]] = []
    failed_items: List[Dict[str, Any]] = []
    results: Optional[Dict[int, bool]] = None


class StockStatusResponse(BaseModel):
    """Response model for stock status"""
    product_id: int
    stock_quantity: int
    reserved_quantity: int
    available_quantity: int
    version: int


class CheckAvailabilityRequest(BaseModel):
    """Request model for checking availability"""
    product_ids: List[int] = Field(..., min_items=1, description="Product IDs to check")
    
    @field_validator('product_ids')
    @classmethod
    def validate_product_ids(cls, v):
        if len(v) > 100:
            raise ValueError('Maximum 100 product IDs allowed')
        return v


# ==================== DEPENDENCIES ====================

def get_db() -> Session:
    """Get database session dependency"""
    with session_scope() as session:
        yield session


def get_inventory_service(session: Session = Depends(get_db)) -> InventoryService:
    """Get inventory service instance"""
    return InventoryService(session)


# ==================== ROUTER ENDPOINTS ====================

@router.post("/reserve", response_model=InventoryResponse)
async def reserve_inventory(
    request: ReserveRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Reserve inventory for ordered items or consumptions.
    
    Uses atomic updates for high concurrency.
    Only succeeds if sufficient stock is available.
    """
    try:
        # Convert items to dict format
        items = [item.model_dump() for item in request.items]
        
        # Execute reservation
        if request.item_type == 'ordered_item':
            result = service.reserve_for_ordered_items(items)
        else:  # consumption
            result = service.reserve_for_consumptions(items)
        
        # Commit the transaction
        service.session.commit()
        
        return InventoryResponse(
            success=result['success'],
            success_count=result['success_count'],
            failed_count=result['failed_count'],
            success_items=result['success_items'],
            failed_items=result['failed_items'],
            results=result.get('results')
        )
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        service.session.rollback()
        logger.error(f"Reservation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reservation failed: {str(e)}"
        )


@router.post("/confirm", response_model=InventoryResponse)
async def confirm_inventory(
    request: ConfirmRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Confirm inventory reservations (deduct from stock).
    
    This moves items from reserved to stock.
    Called when payment succeeds or order is completed.
    """
    try:
        items = [item.model_dump() for item in request.items]
        
        if request.item_type == 'ordered_item':
            result = service.confirm_ordered_items(items)
        else:  # consumption
            result = service.confirm_consumptions(items)
        
        service.session.commit()
        
        return InventoryResponse(
            success=result['success'],
            success_count=result['success_count'],
            failed_count=result['failed_count'],
            success_items=result['success_items'],
            failed_items=result['failed_items']
        )
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        service.session.rollback()
        logger.error(f"Confirmation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confirmation failed: {str(e)}"
        )


@router.post("/release", response_model=InventoryResponse)
async def release_inventory(
    request: ReleaseRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Release inventory reservations (cancel reservation).
    
    This releases reserved quantity back to available.
    Called when order is cancelled or fails.
    """
    try:
        items = [item.model_dump() for item in request.items]
        
        if request.item_type == 'ordered_item':
            result = service.release_ordered_items(items)
        else:  # consumption
            result = service.release_consumptions(items)
        
        service.session.commit()
        
        return InventoryResponse(
            success=result['success'],
            success_count=result['success_count'],
            failed_count=result['failed_count'],
            success_items=result['success_items'],
            failed_items=result['failed_items']
        )
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        service.session.rollback()
        logger.error(f"Release failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Release failed: {str(e)}"
        )


@router.post("/check-and-reserve", response_model=Dict[str, Any])
async def check_and_reserve(
    request: ReserveRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Check availability and reserve in one operation.
    
    Returns detailed results for each item.
    Useful for flash sales and high-concurrency scenarios.
    """
    try:
        items = [{'id': item.id, 'quantity': item.quantity} for item in request.items]
        
        result = service.check_and_reserve(items, request.item_type)
        
        service.session.commit()
        
        return result
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except ValueError as e:
        service.session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        service.session.rollback()
        logger.error(f"Check and reserve failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Operation failed: {str(e)}"
        )


@router.get("/stock/{product_id}", response_model=StockStatusResponse)
async def get_stock_status(
    product_id: int,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Get stock status for a single product.
    """
    try:
        status = service.get_stock_status([product_id])
        
        if product_id not in status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found"
            )
        
        stock = status[product_id]
        
        return StockStatusResponse(
            product_id=product_id,
            stock_quantity=stock['stock'],
            reserved_quantity=stock['reserved'],
            available_quantity=stock['available'],
            version=stock['version']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stock status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock status: {str(e)}"
        )


@router.post("/stock/bulk", response_model=Dict[int, StockStatusResponse])
async def get_bulk_stock_status(
    request: CheckAvailabilityRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Get stock status for multiple products.
    Maximum 100 products per request.
    """
    try:
        status = service.get_stock_status(request.product_ids)
        
        result = {}
        for product_id, stock in status.items():
            result[product_id] = StockStatusResponse(
                product_id=product_id,
                stock_quantity=stock['stock'],
                reserved_quantity=stock['reserved'],
                available_quantity=stock['available'],
                version=stock['version']
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get bulk stock status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock status: {str(e)}"
        )


@router.get("/summary/{product_id}")
async def get_inventory_summary(
    product_id: int,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Get detailed inventory summary for a product.
    """
    try:
        summary = service.get_inventory_summary(product_id)
        
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found"
            )
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get inventory summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get inventory summary: {str(e)}"
        )


@router.get("/available/{product_id}")
async def get_available_quantity(
    product_id: int,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Get available quantity for a product.
    """
    try:
        quantity = service.get_available_quantity(product_id)
        
        return {
            'product_id': product_id,
            'available_quantity': quantity
        }
        
    except Exception as e:
        logger.error(f"Failed to get available quantity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available quantity: {str(e)}"
        )


# ==================== BULK OPERATIONS ====================

@router.post("/bulk/reserve", response_model=Dict[str, Any])
async def bulk_reserve_inventory(
    request: BulkInventoryRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Bulk reserve inventory for both ordered items and consumptions.
    
    This allows reserving both types in a single request.
    """
    try:
        results = {
            'ordered_items': None,
            'consumptions': None,
            'overall_success': True,
            'errors': []
        }
        
        # Process ordered items
        if request.ordered_items:
            items = [item.model_dump() for item in request.ordered_items]
            ordered_result = service.reserve_for_ordered_items(items)
            results['ordered_items'] = ordered_result
            if not ordered_result['success']:
                results['overall_success'] = False
        
        # Process consumptions
        if request.consumptions:
            items = [item.model_dump() for item in request.consumptions]
            consumption_result = service.reserve_for_consumptions(items)
            results['consumptions'] = consumption_result
            if not consumption_result['success']:
                results['overall_success'] = False
        
        service.session.commit()
        
        return results
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        service.session.rollback()
        logger.error(f"Bulk reservation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk reservation failed: {str(e)}"
        )


@router.post("/bulk/confirm", response_model=Dict[str, Any])
async def bulk_confirm_inventory(
    request: BulkInventoryRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Bulk confirm inventory for both ordered items and consumptions.
    """
    try:
        results = {
            'ordered_items': None,
            'consumptions': None,
            'overall_success': True,
            'errors': []
        }
        
        if request.ordered_items:
            items = [item.model_dump() for item in request.ordered_items]
            ordered_result = service.confirm_ordered_items(items)
            results['ordered_items'] = ordered_result
            if not ordered_result['success']:
                results['overall_success'] = False
        
        if request.consumptions:
            items = [item.model_dump() for item in request.consumptions]
            consumption_result = service.confirm_consumptions(items)
            results['consumptions'] = consumption_result
            if not consumption_result['success']:
                results['overall_success'] = False
        
        service.session.commit()
        
        return results
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        service.session.rollback()
        logger.error(f"Bulk confirmation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk confirmation failed: {str(e)}"
        )


@router.post("/bulk/release", response_model=Dict[str, Any])
async def bulk_release_inventory(
    request: BulkInventoryRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Bulk release inventory for both ordered items and consumptions.
    """
    try:
        results = {
            'ordered_items': None,
            'consumptions': None,
            'overall_success': True,
            'errors': []
        }
        
        if request.ordered_items:
            items = [item.model_dump() for item in request.ordered_items]
            ordered_result = service.release_ordered_items(items)
            results['ordered_items'] = ordered_result
            if not ordered_result['success']:
                results['overall_success'] = False
        
        if request.consumptions:
            items = [item.model_dump() for item in request.consumptions]
            consumption_result = service.release_consumptions(items)
            results['consumptions'] = consumption_result
            if not consumption_result['success']:
                results['overall_success'] = False
        
        service.session.commit()
        
        return results
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        service.session.rollback()
        logger.error(f"Bulk release failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk release failed: {str(e)}"
        )


# ==================== HEALTH CHECK ====================

@router.get("/health")
async def inventory_health_check(
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Health check endpoint for inventory service.
    """
    try:
        # Test a simple query
        status = service.get_stock_status([1])
        
        return {
            'status': 'healthy',
            'service': 'inventory',
            'database': 'connected'
        }
        
    except Exception as e:
        logger.error(f"Inventory health check failed: {e}")
        return {
            'status': 'unhealthy',
            'service': 'inventory',
            'error': str(e)
        }
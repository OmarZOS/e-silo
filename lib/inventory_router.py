# lib/inventory_router.py

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session
import logging

from core.database import session_scope
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
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


# ==================== REQUEST MODELS ====================

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
    
    @model_validator(mode='after')
    def validate_at_least_one(self):
        """Ensure at least one of ordered_items or consumptions is provided"""
        if not self.ordered_items and not self.consumptions:
            raise ValueError('At least one of ordered_items or consumptions must be provided')
        return self


class CheckAvailabilityRequest(BaseModel):
    """Request model for checking availability"""
    product_ids: List[int] = Field(..., min_items=1, description="Product IDs to check")
    
    @field_validator('product_ids')
    @classmethod
    def validate_product_ids(cls, v):
        if len(v) > 100:
            raise ValueError('Maximum 100 product IDs allowed')
        return v


# ==================== RESPONSE MODELS ====================

class InventoryItemResult(BaseModel):
    """Result for a single inventory item"""
    id: int = Field(..., description="ID of the item")
    product_id: Optional[int] = Field(None, description="Product ID associated with the item")
    quantity: int = Field(..., description="Quantity processed")
    success: bool = Field(..., description="Whether the operation succeeded")
    reason: Optional[str] = Field(None, description="Reason for failure if any")


class InventoryOperationResponse(BaseModel):
    """Response model for inventory operations"""
    success: bool = Field(..., description="Whether the entire operation succeeded")
    success_count: int = Field(..., description="Number of successfully processed items")
    failed_count: int = Field(..., description="Number of failed items")
    success_items: List[Dict[str, Any]] = Field(default=[], description="List of successfully processed items")
    failed_items: List[Dict[str, Any]] = Field(default=[], description="List of failed items with reasons")
    results: Optional[Dict[int, bool]] = Field(None, description="Detailed results mapping item ID to success status")


class StockStatusResponse(BaseModel):
    """Response model for stock status"""
    product_id: int = Field(..., description="Product ID")
    stock_quantity: int = Field(..., description="Current stock quantity")
    reserved_quantity: int = Field(..., description="Currently reserved quantity")
    available_quantity: int = Field(..., description="Available quantity (stock - reserved)")
    version: int = Field(0, description="Version number for optimistic locking")


class BulkStockStatusResponse(BaseModel):
    """Response model for bulk stock status"""
    products: Dict[int, StockStatusResponse] = Field(..., description="Dictionary of product ID to stock status")


class AvailableQuantityResponse(BaseModel):
    """Response model for available quantity"""
    product_id: int = Field(..., description="Product ID")
    available_quantity: int = Field(..., description="Available quantity")


class InventorySummaryResponse(BaseModel):
    """Response model for inventory summary"""
    id: int = Field(..., description="Product ID")
    stock_quantity: int = Field(..., description="Current stock quantity")
    reserved_quantity: int = Field(..., description="Currently reserved quantity")
    available_quantity: int = Field(..., description="Available quantity (stock - reserved)")
    version: int = Field(0, description="Version number for optimistic locking")


class BulkOperationResponse(BaseModel):
    """Response model for bulk operations"""
    ordered_items: Optional[InventoryOperationResponse] = Field(None, description="Result for ordered items")
    consumptions: Optional[InventoryOperationResponse] = Field(None, description="Result for consumptions")
    overall_success: bool = Field(..., description="Whether the entire bulk operation succeeded")
    errors: List[str] = Field(default=[], description="List of error messages")


class CheckAndReserveResponse(BaseModel):
    """Response model for check and reserve operation"""
    success: bool = Field(..., description="Whether the entire operation succeeded")
    items: List[InventoryItemResult] = Field(..., description="Results for each item")


class HealthCheckResponse(BaseModel):
    """Response model for health check"""
    status: str = Field(..., description="Health status")
    service: str = Field(..., description="Service name")
    database: str = Field(..., description="Database connection status")


# ==================== ERROR RESPONSE MODELS ====================

class ErrorDetail(BaseModel):
    """Detailed error information"""
    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


class ErrorResponse(BaseModel):
    """Standard error response model"""
    detail: str = Field(..., description="Main error message")
    status_code: int = Field(..., description="HTTP status code")
    error_code: Optional[str] = Field(None, description="Application error code")
    errors: Optional[List[ErrorDetail]] = Field(None, description="Detailed error list")
    timestamp: str = Field(..., description="Timestamp of the error")
    path: Optional[str] = Field(None, description="Request path")


# ==================== DEPENDENCIES ====================

def get_db() -> Session:
    """Get database session dependency"""
    with session_scope() as session:
        yield session


def get_inventory_service(session: Session = Depends(get_db)) -> InventoryService:
    """Get inventory service instance"""
    return InventoryService(session)


# ==================== ROUTER ENDPOINTS ====================

@router.post(
    "/reserve",
    response_model=InventoryOperationResponse,
    responses={
        200: {"description": "Reservation successful", "model": InventoryOperationResponse},
        400: {"description": "Bad request", "model": ErrorResponse},
        404: {"description": "Item not found", "model": ErrorResponse},
        409: {"description": "Insufficient stock", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
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
        # Convert items to the format expected by the service
        if request.item_type == 'ordered_item':
            items = [
                {'ordered_item_id': item.id, 'quantity': item.quantity} 
                for item in request.items
            ]
            result = service.reserve_for_ordered_items(items)
        else:  # consumption
            items = [
                {'consumption_id': item.id, 'quantity': item.quantity} 
                for item in request.items
            ]
            result = service.reserve_for_consumptions(items)
        
        return InventoryOperationResponse(**result)
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(
            status_code=e.status_code, 
            detail=e.message
        )
    except Exception as e:
        service.session.rollback()
        logger.error(f"Reservation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reservation failed: {str(e)}"
        )


@router.post(
    "/confirm",
    response_model=InventoryOperationResponse,
    responses={
        200: {"description": "Confirmation successful", "model": InventoryOperationResponse},
        400: {"description": "Bad request", "model": ErrorResponse},
        404: {"description": "Item not found", "model": ErrorResponse},
        409: {"description": "Insufficient stock", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
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
        if request.item_type == 'ordered_item':
            items = [
                {'ordered_item_id': item.id, 'quantity': item.quantity} 
                for item in request.items
            ]
            result = service.confirm_ordered_items(items)
        else:  # consumption
            items = [
                {'consumption_id': item.id, 'quantity': item.quantity} 
                for item in request.items
            ]
            result = service.confirm_consumptions(items)
        
        return InventoryOperationResponse(**result)
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(
            status_code=e.status_code, 
            detail=e.message
        )
    except Exception as e:
        service.session.rollback()
        logger.error(f"Confirmation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confirmation failed: {str(e)}"
        )


@router.post(
    "/release",
    response_model=InventoryOperationResponse,
    responses={
        200: {"description": "Release successful", "model": InventoryOperationResponse},
        400: {"description": "Bad request", "model": ErrorResponse},
        404: {"description": "Item not found", "model": ErrorResponse},
        409: {"description": "Insufficient stock", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
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
        if request.item_type == 'ordered_item':
            items = [
                {'ordered_item_id': item.id, 'quantity': item.quantity} 
                for item in request.items
            ]
            result = service.release_ordered_items(items)
        else:  # consumption
            items = [
                {'consumption_id': item.id, 'quantity': item.quantity} 
                for item in request.items
            ]
            result = service.release_consumptions(items)
        
        return InventoryOperationResponse(**result)
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(
            status_code=e.status_code, 
            detail=e.message
        )
    except Exception as e:
        service.session.rollback()
        logger.error(f"Release failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Release failed: {str(e)}"
        )


@router.post(
    "/check-and-reserve",
    response_model=CheckAndReserveResponse,
    responses={
        200: {"description": "Check and reserve successful", "model": CheckAndReserveResponse},
        400: {"description": "Bad request", "model": ErrorResponse},
        404: {"description": "Item not found", "model": ErrorResponse},
        409: {"description": "Insufficient stock", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
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
        # Convert items to the format expected by check_and_reserve
        items = [{'id': item.id, 'quantity': item.quantity} for item in request.items]
        
        result = service.check_and_reserve(items, request.item_type)
        
        return CheckAndReserveResponse(**result)
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(
            status_code=e.status_code, 
            detail=e.message
        )
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


@router.get(
    "/stock/{product_id}",
    response_model=StockStatusResponse,
    responses={
        200: {"description": "Stock status retrieved", "model": StockStatusResponse},
        404: {"description": "Product not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_stock_status(
    product_id: int,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Get stock status for a single product.
    """
    try:
        status_data = service.get_stock_status([product_id])
        
        if product_id not in status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found"
            )
        
        stock = status_data[product_id]
        
        return StockStatusResponse(
            product_id=product_id,
            stock_quantity=stock.get('stock', 0),
            reserved_quantity=stock.get('reserved', 0),
            available_quantity=stock.get('available', 0),
            version=stock.get('version', 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stock status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock status: {str(e)}"
        )


@router.post(
    "/stock/bulk",
    response_model=Dict[int, StockStatusResponse],
    responses={
        200: {"description": "Bulk stock status retrieved"},
        400: {"description": "Bad request", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_bulk_stock_status(
    request: CheckAvailabilityRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Get stock status for multiple products.
    Maximum 100 products per request.
    """
    try:
        status_data = service.get_stock_status(request.product_ids)
        
        result = {}
        for product_id, stock in status_data.items():
            result[product_id] = StockStatusResponse(
                product_id=product_id,
                stock_quantity=stock.get('stock', 0),
                reserved_quantity=stock.get('reserved', 0),
                available_quantity=stock.get('available', 0),
                version=stock.get('version', 0)
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get bulk stock status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock status: {str(e)}"
        )


@router.get(
    "/summary/{product_id}",
    response_model=InventorySummaryResponse,
    responses={
        200: {"description": "Inventory summary retrieved", "model": InventorySummaryResponse},
        404: {"description": "Product not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
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
        
        return InventorySummaryResponse(
            id=summary.get('id'),
            stock_quantity=summary.get('stock_quantity', 0),
            reserved_quantity=summary.get('reserved_quantity', 0),
            available_quantity=summary.get('available_quantity', 0),
            version=summary.get('version', 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get inventory summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get inventory summary: {str(e)}"
        )


@router.get(
    "/available/{product_id}",
    response_model=AvailableQuantityResponse,
    responses={
        200: {"description": "Available quantity retrieved", "model": AvailableQuantityResponse},
        404: {"description": "Product not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_available_quantity(
    product_id: int,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Get available quantity for a product.
    """
    try:
        quantity = service.get_available_quantity(product_id)
        
        return AvailableQuantityResponse(
            product_id=product_id,
            available_quantity=quantity
        )
        
    except Exception as e:
        logger.error(f"Failed to get available quantity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available quantity: {str(e)}"
        )


# ==================== BULK OPERATIONS ====================

@router.post(
    "/bulk/reserve",
    response_model=BulkOperationResponse,
    responses={
        200: {"description": "Bulk reservation successful", "model": BulkOperationResponse},
        400: {"description": "Bad request", "model": ErrorResponse},
        404: {"description": "Item not found", "model": ErrorResponse},
        409: {"description": "Insufficient stock", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def bulk_reserve_inventory(
    request: BulkInventoryRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Bulk reserve inventory for both ordered items and consumptions.
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
            items = [
                {'ordered_item_id': item.id, 'quantity': item.quantity} 
                for item in request.ordered_items
            ]
            ordered_result = service.reserve_for_ordered_items(items)
            results['ordered_items'] = InventoryOperationResponse(**ordered_result)
            if not ordered_result.get('success', False):
                results['overall_success'] = False
        
        # Process consumptions
        if request.consumptions:
            items = [
                {'consumption_id': item.id, 'quantity': item.quantity} 
                for item in request.consumptions
            ]
            consumption_result = service.reserve_for_consumptions(items)
            results['consumptions'] = InventoryOperationResponse(**consumption_result)
            if not consumption_result.get('success', False):
                results['overall_success'] = False
        
        return BulkOperationResponse(**results)
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(
            status_code=e.status_code, 
            detail=e.message
        )
    except Exception as e:
        service.session.rollback()
        logger.error(f"Bulk reservation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk reservation failed: {str(e)}"
        )

@router.post(
    "/bulk/confirm",
    response_model=BulkOperationResponse,
    responses={
        200: {"description": "Bulk confirmation successful", "model": BulkOperationResponse},
        400: {"description": "Bad request", "model": ErrorResponse},
        404: {"description": "Item not found", "model": ErrorResponse},
        409: {"description": "Insufficient stock", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def bulk_confirm_inventory(
    request: BulkInventoryRequest,
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Bulk confirm inventory for both ordered items and consumptions ATOMICALLY.
    
    ALL items must succeed, or NONE will be confirmed.
    This ensures data consistency when confirming orders that include both products and services.
    """
    try:
        # Prepare items for both types
        ordered_items_data = []
        consumptions_data = []
        
        if request.ordered_items:
            ordered_items_data = [
                {'ordered_item_id': item.id, 'quantity': item.quantity} 
                for item in request.ordered_items
            ]
        
        if request.consumptions:
            consumptions_data = [
                {'consumption_id': item.id, 'quantity': item.quantity} 
                for item in request.consumptions
            ]
        
        # Atomic confirmation - both must succeed
        result = service.bulk_confirm_atomic(ordered_items_data, consumptions_data)
        
        return BulkOperationResponse(**result)
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(
            status_code=e.status_code, 
            detail=e.message
        )
    except Exception as e:
        service.session.rollback()
        logger.error(f"Bulk confirmation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk confirmation failed: {str(e)}"
        )


@router.post(
    "/bulk/release",
    response_model=BulkOperationResponse,
    responses={
        200: {"description": "Bulk release successful", "model": BulkOperationResponse},
        400: {"description": "Bad request", "model": ErrorResponse},
        404: {"description": "Item not found", "model": ErrorResponse},
        409: {"description": "Insufficient stock", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
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
            items = [
                {'ordered_item_id': item.id, 'quantity': item.quantity} 
                for item in request.ordered_items
            ]
            ordered_result = service.release_ordered_items(items)
            results['ordered_items'] = InventoryOperationResponse(**ordered_result)
            if not ordered_result.get('success', False):
                results['overall_success'] = False
        
        if request.consumptions:
            items = [
                {'consumption_id': item.id, 'quantity': item.quantity} 
                for item in request.consumptions
            ]
            consumption_result = service.release_consumptions(items)
            results['consumptions'] = InventoryOperationResponse(**consumption_result)
            if not consumption_result.get('success', False):
                results['overall_success'] = False
        
        return BulkOperationResponse(**results)
        
    except APIException as e:
        service.session.rollback()
        raise HTTPException(
            status_code=e.status_code, 
            detail=e.message
        )
    except Exception as e:
        service.session.rollback()
        logger.error(f"Bulk release failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk release failed: {str(e)}"
        )


# ==================== HEALTH CHECK ====================

@router.get(
    "/health",
    response_model=HealthCheckResponse,
    responses={
        200: {"description": "Health check passed", "model": HealthCheckResponse},
        500: {"description": "Health check failed", "model": HealthCheckResponse}
    }
)
async def inventory_health_check(
    service: InventoryService = Depends(get_inventory_service)
):
    """
    Health check endpoint for inventory service.
    """
    try:
        status = service.get_stock_status([1])
        
        return HealthCheckResponse(
            status='healthy',
            service='inventory',
            database='connected'
        )
        
    except Exception as e:
        logger.error(f"Inventory health check failed: {e}")
        return HealthCheckResponse(
            status='unhealthy',
            service='inventory',
            database='disconnected'
        )
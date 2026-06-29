# routers/service_order_router.py

from typing import Dict, List, Optional, Tuple, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from decimal import Decimal
from datetime import datetime
import logging
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from core.models import (
    Cart, Product, OrderedItem, PlacedOrder, 
    AppUser, ProductProvider, ManagementRule,
    ProvidedService, OrderedService, ServiceResourceRequirement,
    ServicePackage, ServicePackageItem
)
from core.storage_broker import (
    get_engine, transactional, session_scope,
    insert_record_transactional, batch_insert_transactional
)
from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import (
    HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, 
    HTTP_409_CONFLICT, HTTP_422_UNPROCESSABLE_ENTITY
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/service-orders", tags=["service-orders"])


# ==================== Pydantic Models ====================

class ServiceOrderRequest(BaseModel):
    """Request model for creating a service order"""
    cart_id: Optional[int] = Field(None, description="Existing cart ID")
    placed_order_id: Optional[int] = Field(None, description="Existing placed order ID")
    service_quantities: Dict[int, int] = Field(
        ..., 
        description="Map of provided_service_id to quantity",
        min_items=1
    )
    scheduled_at: Optional[datetime] = Field(None, description="Scheduled service time")
    notes: Optional[str] = Field(None, description="Additional notes for the order")
    
    @model_validator(mode='after')
    def validate_ids(self):
        """Ensure only one ID is provided"""
        # Both are None
        if self.cart_id is None and self.placed_order_id is None:
            raise ValueError('Either cart_id or placed_order_id must be provided')
        
        # Both are provided
        if self.placed_order_id is not None and self.placed_order_id is not None:
            raise ValueError('Cannot provide both cart_id and placed_order_id')
        
        return self
    
    @field_validator('service_quantities')
    def validate_quantities(cls, v):
        """Ensure all quantities are positive"""
        for service_id, quantity in v.items():
            if quantity <= 0:
                raise ValueError(f'Quantity for service {service_id} must be positive')
            if quantity > 100:  # Reasonable limit for services
                raise ValueError(f'Quantity for service {service_id} exceeds maximum limit')
        return v


class ServiceOrderResponse(BaseModel):
    """Response model for service order creation"""
    success: bool
    message: str
    order_id: Optional[int] = None
    cart_id: Optional[int] = None
    ordered_services: List[Dict] = []
    resource_deductions: List[Dict] = []
    resource_availability: Dict[int, Dict] = {}
    errors: List[str] = []


class ServiceResourceAvailability(BaseModel):
    """Service resource availability check result"""
    service_id: int
    service_name: str
    available: bool
    requested_quantity: int
    resources: List[Dict] = []
    reason: Optional[str] = None


class ResourceRequirementCheck(BaseModel):
    """Individual resource requirement check"""
    product_id: int
    product_name: str
    required_quantity: int
    available_quantity: int
    available: bool
    reason: Optional[str] = None


# ==================== Router Endpoints ====================

@router.post("/create", response_model=ServiceOrderResponse)
async def create_service_order(request: ServiceOrderRequest):
    """
    Create a service order with resource validation and inventory deductions.
    
    1. Validate cart/order ID (exactly one provided)
    2. Check service availability and resource requirements
    3. Deduct required product quantities for service resources
    4. Create OrderedService records
    5. Link to cart/placed order
    """
    try:
        # Validate that exactly one ID is provided
        if request.cart_id is None and request.placed_order_id is None:
            raise APIException(
                status_code=HTTP_400_BAD_REQUEST,
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Either cart_id or placed_order_id must be provided"
            )
        
        # Step 1: Get the cart/order context
        cart = None
        placed_order = None
        context = {}
        
        if request.cart_id:
            cart = get_cart_with_services(request.cart_id)
            if not cart:
                raise APIException(
                    status_code=HTTP_404_NOT_FOUND,
                    error_code=ErrorCode.DATA_ERROR,
                    message=f"Cart with ID {request.cart_id} not found"
                )
            context['cart'] = cart
            context['user_id'] = cart.cart_selling_user
            context['provider_id'] = cart.cart_product_provider_id
        else:
            placed_order = get_placed_order_by_id(request.placed_order_id)
            if not placed_order:
                raise APIException(
                    status_code=HTTP_404_NOT_FOUND,
                    error_code=ErrorCode.DATA_ERROR,
                    message=f"Placed order with ID {request.placed_order_id} not found"
                )
            context['placed_order'] = placed_order
            context['user_id'] = placed_order.placed_order_user
            context['provider_id'] = get_order_provider_id(placed_order)
        
        # Step 2: Check service availability and resource requirements
        service_check = await check_service_availability(
            request.service_quantities,
            context['provider_id']
        )
        
        # If any service is not available, return error response
        unavailable_services = [
            s for s in service_check if not s.available
        ]
        
        if unavailable_services:
            return ServiceOrderResponse(
                success=False,
                message="Some services are not available due to resource constraints",
                resource_availability={
                    s.service_id: {
                        'available': s.available,
                        'requested': s.requested_quantity,
                        'resources': s.resources,
                        'reason': s.reason
                    }
                    for s in unavailable_services
                },
                errors=[
                    f"Service {s.service_id} ({s.service_name}): {s.reason}"
                    for s in unavailable_services
                ]
            )
        
        # Step 3: Process the service order in a transaction
        result = await process_service_order_in_transaction(
            context=context,
            service_quantities=request.service_quantities,
            service_data=service_check,
            scheduled_at=request.scheduled_at,
            notes=request.notes
        )
        
        return ServiceOrderResponse(
            success=True,
            message="Service order created successfully",
            order_id=result.get('placed_order_id'),
            cart_id=result.get('cart_id'),
            ordered_services=result.get('ordered_services', []),
            resource_deductions=result.get('resource_deductions', []),
            resource_availability={
                s.service_id: {
                    'available': s.available,
                    'requested': s.requested_quantity,
                    'resources': [
                        {
                            'product_id': r.product_id,
                            'product_name': r.product_name,
                            'required': r.required_quantity,
                            'available': r.available_quantity
                        }
                        for r in s.resources
                    ]
                }
                for s in service_check
            }
        )
        
    except APIException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error creating service order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


# ==================== Core Business Logic ====================

@transactional
def process_service_order_in_transaction(
    context: Dict, 
    service_quantities: Dict[int, int],
    service_data: List[ServiceResourceAvailability],
    scheduled_at: Optional[datetime] = None,
    notes: Optional[str] = None,
    session=None
) -> Dict:
    """
    Process the service order within a single transaction.
    
    Steps:
    1. Get or create PlacedOrder
    2. Deduct product quantities for service resources
    3. Create OrderedService records
    4. Link to cart if provided
    """
    try:
        cart = context.get('cart')
        placed_order = context.get('placed_order')
        user_id = context.get('user_id')
        provider_id = context.get('provider_id')
        
        # Create placed order if not provided
        if not placed_order:
            placed_order = PlacedOrder(
                placed_order_user=user_id,
                placed_order_provider=provider_id,
                placed_order_status='pending',
                placed_order_created_at=datetime.utcnow()
            )
            session.add(placed_order)
            session.flush()
            session.refresh(placed_order)
            logger.info(f"Created new placed order: {placed_order.id_placed_order}")
        
        # Update cart status if cart exists
        if cart:
            cart.cart_status = 'checkout'
            cart.cart_updated_at = datetime.utcnow()
            session.add(cart)
            session.flush()
        
        # Track resource deductions for response
        resource_deductions = []
        ordered_services = []
        total_amount = Decimal('0')
        
        # Process each service
        for service_id, requested_qty in service_quantities.items():
            # Get service data
            service_info = next(
                (s for s in service_data if s.service_id == service_id),
                None
            )
            
            if not service_info:
                raise ValueError(f"Service {service_id} not found in availability check")
            
            # Get the actual service
            service = session.query(ProvidedService).filter(
                ProvidedService.provided_service_id == service_id,
                ProvidedService.provided_service_is_active == 1
            ).first()
            
            if not service:
                raise ValueError(f"Service {service_id} not found or inactive")
            
            # Deduct resources for this service
            service_resource_deductions = []
            
            # Get resource requirements for this service
            resources = session.query(ServiceResourceRequirement).filter(
                ServiceResourceRequirement.service_resource_requirement_service_id == service_id
            ).all()
            
            for resource in resources:
                # Calculate total quantity needed
                total_required = resource.service_resource_requirement_quantity * requested_qty
                
                # Get the product
                product = session.query(Product).filter(
                    Product.id_product == resource.service_resource_requirement_product_ref
                ).first()
                
                if not product:
                    raise ValueError(
                        f"Product {resource.service_resource_requirement_product_ref} "
                        f"not found for resource requirement"
                    )
                
                # Deduct from product quantity
                original_qty = product.product_quantity or 0
                product.product_quantity = original_qty - total_required
                
                # Update product
                session.add(product)
                
                # Track deduction
                resource_deduction = {
                    'product_id': product.id_product,
                    'product_name': product.product_name,
                    'original_quantity': original_qty,
                    'deducted_quantity': total_required,
                    'remaining_quantity': product.product_quantity,
                    'service_id': service_id,
                    'resource_requirement_id': resource.service_resource_requirement_id
                }
                service_resource_deductions.append(resource_deduction)
                resource_deductions.append(resource_deduction)
                
                logger.info(
                    f"Deducted {total_required} units of product {product.id_product} "
                    f"for service {service_id}. Remaining: {product.product_quantity}"
                )
            
            # Calculate service price
            unit_price = service.provided_service_final_price or service.provided_service_base_price
            if unit_price is None:
                unit_price = Decimal('0')
            
            total_price = Decimal(str(unit_price)) * requested_qty
            total_amount += total_price
            
            # Create ordered service
            ordered_service = OrderedService(
                ordered_service_cart_id=cart.cart_id if cart else None,
                ordered_service_service_id=service_id,
                ordered_service_quantity=requested_qty,
                ordered_service_unit_price=unit_price,
                ordered_service_total_price=float(total_price),
                ordered_service_notes=notes,
                ordered_service_scheduled_at=scheduled_at,
                ordered_service_delivery_status='pending',
                ordered_service_delivery_fee=0.0  # Calculate as needed
            )
            session.add(ordered_service)
            session.flush()
            session.refresh(ordered_service)
            
            ordered_services.append({
                'id': ordered_service.ordered_service_id,
                'service_id': service_id,
                'service_name': service.provided_service_name,
                'quantity': requested_qty,
                'unit_price': float(unit_price),
                'total_price': float(total_price),
                'scheduled_at': scheduled_at.isoformat() if scheduled_at else None,
                'resource_deductions': service_resource_deductions
            })
        
        # Update placed order total
        placed_order.placed_order_total = float(total_amount)
        placed_order.placed_order_last_update = datetime.utcnow()
        session.add(placed_order)
        
        # Update cart total if cart exists
        if cart:
            cart.cart_total_amount = total_amount
            session.add(cart)
        
        session.flush()
        
        return {
            'placed_order_id': placed_order.id_placed_order,
            'cart_id': cart.cart_id if cart else None,
            'ordered_services': ordered_services,
            'resource_deductions': resource_deductions
        }
        
    except Exception as e:
        logger.error(f"Transaction failed for service order processing: {e}")
        session.rollback()
        raise


async def check_service_availability(
    service_quantities: Dict[int, int],
    provider_id: int
) -> List[ServiceResourceAvailability]:
    """
    Check if all services are available and have sufficient resources.
    
    Validates:
    - Services exist and are active
    - Services belong to the provider
    - All resource requirements can be fulfilled
    - Product quantities are sufficient
    """
    results = []
    
    with session_scope() as session:
        for service_id, requested_qty in service_quantities.items():
            # Query service with provider validation
            service = session.query(ProvidedService).filter(
                ProvidedService.provided_service_id == service_id,
                ProvidedService.provided_service_product_provider_id == provider_id,
                ProvidedService.provided_service_is_active == 1
            ).first()
            
            if not service:
                results.append(ServiceResourceAvailability(
                    service_id=service_id,
                    service_name="Unknown Service",
                    available=False,
                    requested_quantity=requested_qty,
                    resources=[],
                    reason="Service not found or not available from this provider"
                ))
                continue
            
            # Get resource requirements
            resources = session.query(ServiceResourceRequirement).filter(
                ServiceResourceRequirement.service_resource_requirement_service_id == service_id
            ).all()
            
            # If no resources, service is available
            if not resources:
                results.append(ServiceResourceAvailability(
                    service_id=service_id,
                    service_name=service.provided_service_name,
                    available=True,
                    requested_quantity=requested_qty,
                    resources=[]
                ))
                continue
            
            # Check each resource requirement
            resource_checks = []
            all_resources_available = True
            
            for resource in resources:
                # Get product and check availability
                product = session.query(Product).filter(
                    Product.id_product == resource.service_resource_requirement_product_ref
                ).first()
                
                if not product:
                    resource_checks.append(ResourceRequirementCheck(
                        product_id=resource.service_resource_requirement_product_ref,
                        product_name="Unknown Product",
                        required_quantity=resource.service_resource_requirement_quantity * requested_qty,
                        available_quantity=0,
                        available=False,
                        reason="Product not found"
                    ))
                    all_resources_available = False
                    continue
                
                required_total = resource.service_resource_requirement_quantity * requested_qty
                available_qty = product.product_quantity or 0
                
                is_available = available_qty >= required_total
                
                resource_check = ResourceRequirementCheck(
                    product_id=product.id_product,
                    product_name=product.product_name,
                    required_quantity=required_total,
                    available_quantity=available_qty,
                    available=is_available,
                    reason=(
                        f"Insufficient stock. Available: {available_qty}, Required: {required_total}"
                        if not is_available else None
                    )
                )
                resource_checks.append(resource_check)
                
                if not is_available:
                    all_resources_available = False
            
            # Compile result
            results.append(ServiceResourceAvailability(
                service_id=service_id,
                service_name=service.provided_service_name,
                available=all_resources_available,
                requested_quantity=requested_qty,
                resources=[r.dict() for r in resource_checks],
                reason=(
                    "Resource requirements cannot be fulfilled"
                    if not all_resources_available else None
                )
            ))
    
    return results


# ==================== Helper Functions ====================

def get_cart_with_services(cart_id: int):
    """Get cart with service relationships loaded"""
    with session_scope() as session:
        return session.query(Cart).filter(
            Cart.cart_id == cart_id
        ).options(
            joinedload(Cart.ordered_service)
        ).first()


def get_placed_order_by_id(placed_order_id: int):
    """Get placed order by ID"""
    with session_scope() as session:
        return session.query(PlacedOrder).filter(
            PlacedOrder.id_placed_order == placed_order_id
        ).first()


def get_order_provider_id(placed_order: PlacedOrder) -> Optional[int]:
    """Get the provider ID from a placed order"""
    with session_scope() as session:
        # Get provider from ordered services
        ordered_service = session.query(OrderedService).filter(
            OrderedService.ordered_service_cart_id == placed_order.id_placed_order
        ).first()
        
        if ordered_service and ordered_service.ordered_service_service_id:
            service = session.query(ProvidedService).filter(
                ProvidedService.provided_service_id == ordered_service.ordered_service_service_id
            ).first()
            if service:
                return service.provided_service_product_provider_id
        
        # Fallback to the order's provider if stored
        return placed_order.placed_order_provider


# ==================== Additional Endpoints ====================

@router.post("/availability-check")
async def check_service_availability_endpoint(request: ServiceOrderRequest):
    """
    Check service availability and resource requirements without creating an order.
    Useful for the frontend to validate before checkout.
    """
    try:
        # Validate exactly one ID is provided
        if request.cart_id is None and request.placed_order_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either cart_id or placed_order_id must be provided"
            )
        
        # Get provider ID
        provider_id = None
        if request.cart_id:
            cart = get_cart_with_services(request.cart_id)
            if cart:
                provider_id = cart.cart_product_provider_id
        else:
            placed_order = get_placed_order_by_id(request.placed_order_id)
            if placed_order:
                provider_id = get_order_provider_id(placed_order)
        
        if not provider_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not determine provider for this order"
            )
        
        availability = await check_service_availability(
            request.service_quantities,
            provider_id
        )
        
        return {
            "success": True,
            "service_availability": {
                a.service_id: {
                    "available": a.available,
                    "service_name": a.service_name,
                    "requested_quantity": a.requested_quantity,
                    "resources": a.resources,
                    "reason": a.reason
                }
                for a in availability
            },
            "all_available": all(a.available for a in availability)
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error checking service availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking service availability: {str(e)}"
        )


@router.post("/package-order")
async def create_service_package_order(
    cart_id: int,
    service_package_id: int,
    quantity: int = 1
):
    """
    Create an order for a service package.
    This will automatically add all services from the package.
    """
    try:
        with session_scope() as session:
            # Get the service package
            package = session.query(ServicePackage).filter(
                ServicePackage.service_package_id == service_package_id,
                ServicePackage.service_package_is_active == 1
            ).first()
            
            if not package:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Service package not found or inactive"
                )
            
            # Get package items
            package_items = session.query(ServicePackageItem).filter(
                ServicePackageItem.service_package_item_package_id == service_package_id
            ).all()
            
            if not package_items:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Service package has no items"
                )
            
            # Build service quantities
            service_quantities = {}
            for item in package_items:
                service_id = item.service_package_item_service_id
                item_quantity = item.service_package_item_quantity or 1
                service_quantities[service_id] = service_quantities.get(service_id, 0) + (item_quantity * quantity)
            
            # Create the order request
            order_request = ServiceOrderRequest(
                cart_id=cart_id,
                placed_order_id=None,
                service_quantities=service_quantities,
                notes=f"Order from service package: {package.service_package_name}"
            )
            
            # Process the order
            return await create_service_order(order_request)
            
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creating package order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating package order: {str(e)}"
        )


# ==================== Batch Operations ====================

@router.post("/batch-create")
async def batch_create_service_orders(orders: List[ServiceOrderRequest]):
    """
    Create multiple service orders in batch.
    Useful for bulk operations or migrations.
    """
    results = []
    errors = []
    
    for idx, order_request in enumerate(orders):
        try:
            result = await create_service_order(order_request)
            results.append({
                "index": idx,
                "success": result.success,
                "data": result.dict()
            })
        except Exception as e:
            errors.append({
                "index": idx,
                "error": str(e)
            })
    
    return {
        "total": len(orders),
        "successful": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    }
# routers/order_router.py

import datetime
from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from decimal import Decimal
import logging
from sqlalchemy.orm import Session

from core.exceptions.handler import APIException
from core.exceptions.error_codes import ErrorCode
from core.exceptions.http_status import (
    HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, 
    HTTP_409_CONFLICT, HTTP_422_UNPROCESSABLE_ENTITY
)
from core.models import Cart, ManagementRule, OrderedItem, Product, PlacedOrder
from core.storage_broker import session_scope
from core.transaction import transactional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


# ==================== Pydantic Models ====================

class OrderRequest(BaseModel):
    """Request model for creating an order"""
    cart_id: Optional[int] = Field(None, description="Existing cart ID")
    placed_order_id: Optional[int] = Field(None, description="Existing placed order ID")
    product_quantities: Dict[int, int] = Field(
        ..., 
        description="Map of product_id to quantity",
        min_items=1
    )
    
    @model_validator(mode='after')
    def validate_ids(self):
        """Ensure only one ID is provided"""
        # Both are None
        if self.cart_id is None and self.placed_order_id is None:
            raise ValueError('Either cart_id or placed_order_id must be provided')
        
        # Both are provided
        if self.cart_id is not None and self.placed_order_id is not None:
            raise ValueError('Cannot provide both cart_id and placed_order_id')
        
        return self
            
    @field_validator('product_quantities')
    def validate_quantities(cls, v):
        """Ensure all quantities are positive"""
        for product_id, quantity in v.items():
            if quantity <= 0:
                raise ValueError(f'Quantity for product {product_id} must be positive')
            if quantity > 1000:  # Reasonable limit
                raise ValueError(f'Quantity for product {product_id} exceeds maximum limit')
        return v


class OrderResponse(BaseModel):
    """Response model for order creation"""
    success: bool
    message: str
    order_id: Optional[int] = None
    cart_id: Optional[int] = None
    ordered_items: List[Dict] = []
    product_availability: Dict[int, Dict] = {}
    errors: List[str] = []


class ProductAvailability(BaseModel):
    """Product availability check result"""
    product_id: int
    available: bool
    requested_quantity: int
    available_quantity: int
    reason: Optional[str] = None


# ==================== Router Endpoints ====================

@router.post("/create", response_model=OrderResponse)
async def create_order(request: OrderRequest):
    """
    Create an order with product validation and inventory checks.
    
    1. Validate cart/order ID (exactly one provided)
    2. Check product availability
    3. Create OrderedItem records
    4. Update product quantities (deduct inventory)
    5. Create PlacedOrder if needed
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
            cart = get_cart_by_id(request.cart_id)
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
            # Get provider from first ordered item or from relationship
            context['provider_id'] = get_order_provider_id(placed_order)
        
        # Step 2: Check product availability and validate providers
        availability_check = await check_product_availability(
            request.product_quantities,
            context['provider_id']
        )
        
        # If any product is not available, return error response
        unavailable_products = [
            p for p in availability_check if not p.available
        ]
        
        if unavailable_products:
            return OrderResponse(
                success=False,
                message="Some products are not available",
                product_availability={
                    p.product_id: {
                        'available': p.available,
                        'requested': p.requested_quantity,
                        'available_qty': p.available_quantity,
                        'reason': p.reason
                    }
                    for p in unavailable_products
                },
                errors=[
                    f"Product {p.product_id}: {p.reason}"
                    for p in unavailable_products
                ]
            )
        
        # Step 3: Process the order in a transaction
        result = await process_order_in_transaction(
            context=context,
            product_quantities=request.product_quantities,
            products_data=availability_check
        )
        
        return OrderResponse(
            success=True,
            message="Order created successfully",
            order_id=result.get('placed_order_id'),
            cart_id=result.get('cart_id'),
            ordered_items=result.get('ordered_items', []),
            product_availability={
                p.product_id: {
                    'available': p.available,
                    'requested': p.requested_quantity,
                    'available_qty': p.available_quantity
                }
                for p in availability_check
            }
        )
        
    except APIException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error creating order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


# ==================== Core Business Logic ====================

@transactional
def process_order_in_transaction(context: Dict, product_quantities: Dict[int, int], 
                                 products_data: List[ProductAvailability], session=None):
    """
    Process the order within a single transaction.
    
    Steps:
    1. Get or create PlacedOrder
    2. Create OrderedItem records for each product
    3. Update product inventory
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
        
        # Create ordered items
        ordered_items = []
        total_amount = Decimal('0')
        
        for product_id, requested_qty in product_quantities.items():
            # Find product data from availability check
            product_data = next(
                (p for p in products_data if p.product_id == product_id), 
                None
            )
            
            if not product_data:
                # This shouldn't happen since we validated above
                raise ValueError(f"Product {product_id} not found in availability check")
            
            # Get the actual product
            product = session.query(Product).filter(
                Product.id_product == product_id
            ).first()
            
            if not product:
                raise ValueError(f"Product {product_id} not found")
            
            # Calculate pricing (you might have more complex logic here)
            unit_price = product.product_price
            total_price = unit_price * requested_qty
            total_amount += total_price
            
            # Create ordered item
            ordered_item = OrderedItem(
                ordered_product_id=product_id,
                ordered_quantity=requested_qty,
                unit_price=unit_price,
                applied_vat=Decimal('0'),  # Calculate VAT as needed
                product_discount=Decimal('0'),  # Apply discounts as needed
                order_ref=placed_order.id_placed_order,
                ordered_item_cart_ref=cart.cart_id if cart else None,
                ordered_item_delivery_status='pending',
                ordered_item_delivery_fee=Decimal('0')  # Calculate delivery fee as needed
            )
            session.add(ordered_item)
            session.flush()
            session.refresh(ordered_item)
            ordered_items.append(ordered_item)
            
            # Update product quantity (deduct inventory)
            product.product_quantity -= requested_qty
            session.add(product)
            
            logger.info(
                f"Deducted {requested_qty} from product {product_id}, "
                f"remaining: {product.product_quantity}"
            )
        
        # Update placed order total if needed
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
            'ordered_items': [
                {
                    'id': item.id_ordered_item,
                    'product_id': item.ordered_product_id,
                    'quantity': item.ordered_quantity,
                    'unit_price': float(item.unit_price),
                    'total_price': float(item.unit_price * item.ordered_quantity)
                }
                for item in ordered_items
            ]
        }
        
    except Exception as e:
        logger.error(f"Transaction failed for order processing: {e}")
        session.rollback()
        raise


async def check_product_availability(product_quantities: Dict[int, int], provider_id: int) -> List[ProductAvailability]:
    """
    Check if all products are available in sufficient quantities.
    
    Also validates:
    - Products belong to the correct provider
    - Products are visible
    - Products have sufficient stock
    """
    results = []
    
    with session_scope() as session:
        for product_id, requested_qty in product_quantities.items():
            # Query product with provider validation
            product = session.query(Product).filter(
                Product.id_product == product_id,
                Product.product_provider_id == provider_id,
                Product.product_visibility == 'VISIBLE'
            ).first()
            
            if not product:
                results.append(ProductAvailability(
                    product_id=product_id,
                    available=False,
                    requested_quantity=requested_qty,
                    available_quantity=0,
                    reason=f"Product not found or not available from this provider"
                ))
                continue
            
            
            # Check stock availability
            if product.product_quantity < requested_qty:
                results.append(ProductAvailability(
                    product_id=product_id,
                    available=False,
                    requested_quantity=requested_qty,
                    available_quantity=product.product_quantity or 0,
                    reason=f"Insufficient stock. Available: {product.product_quantity or 0}, Requested: {requested_qty}"
                ))
                continue
            
            # Check if product is active/sellable (additional checks)
            if product.product_quantity is None or product.product_quantity <= 0:
                results.append(ProductAvailability(
                    product_id=product_id,
                    available=False,
                    requested_quantity=requested_qty,
                    available_quantity=0,
                    reason="Product is out of stock"
                ))
                continue
            
            # Product is available
            results.append(ProductAvailability(
                product_id=product_id,
                available=True,
                requested_quantity=requested_qty,
                available_quantity=product.product_quantity or 0
            ))
    
    return results


# ==================== Helper Functions ====================

def get_cart_by_id(cart_id: int):
    """Get cart by ID with relevant joins"""
    with session_scope() as session:
        return session.query(Cart).filter(
            Cart.cart_id == cart_id
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
        # Get provider from ordered items
        ordered_item = session.query(OrderedItem).filter(
            OrderedItem.order_ref == placed_order.id_placed_order
        ).first()
        
        if ordered_item and ordered_item.ordered_product_id:
            product = session.query(Product).filter(
                Product.id_product == ordered_item.ordered_product_id
            ).first()
            if product:
                return product.product_provider_id
        
        # Fallback to the order's provider if stored
        return placed_order.placed_order_provider


# ==================== Additional Endpoints ====================

@router.post("/availability-check")
async def check_availability(request: OrderRequest):
    """
    Check product availability without creating an order.
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
            cart = get_cart_by_id(request.cart_id)
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
        
        availability = await check_product_availability(
            request.product_quantities,
            provider_id
        )
        
        return {
            "success": True,
            "product_availability": {
                p.product_id: {
                    "available": p.available,
                    "requested_quantity": p.requested_quantity,
                    "available_quantity": p.available_quantity,
                    "reason": p.reason
                }
                for p in availability
            },
            "all_available": all(p.available for p in availability)
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking product availability: {str(e)}"
        )
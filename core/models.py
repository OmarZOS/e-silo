from sqlalchemy import Column, DECIMAL, Date, DateTime, Enum, Float, ForeignKeyConstraint, Index, Integer, JSON, String, TIMESTAMP, Text, text
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class PlacedOrder(Base):
    __tablename__ = 'placed_order'
    __table_args__ = (
        ForeignKeyConstraint(['ordering_user_id'], ['app_user.id_app_user'], ondelete='RESTRICT', onupdate='RESTRICT', name='fk_placed_order_1'),
        Index('fk_placed_order_1_idx', 'ordering_user_id'),
    )

    id_placed_order = Column(Integer, primary_key=True)
    order_discount = Column(Float(asdecimal=True))
    total_price = Column(Float(asdecimal=True))
    ordering_user_id = Column(Integer)
    placed_order_state = Column(Enum('PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'REFUNDED'), server_default=text("'PENDING'"))
    placed_order_last_mod = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    placed_order_receipt_ref = Column(Integer)
    placed_order_creation = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))

    ordering_user = relationship('AppUser', back_populates='placed_order')
    ordered_item = relationship('OrderedItem', back_populates='placed_order')


class AppUser(Base):
    __tablename__ = 'app_user'

    id_app_user = Column(Integer, primary_key=True)
    app_user_name = Column(String(100))
    app_user_password = Column(String(256))
    app_user_type = Column(Enum('admin', 'provider', 'customer', 'patient', 'guest'), server_default=text("'customer'"))
    app_user_preferences = Column(Text)
    app_user_last_active = Column(TIMESTAMP)
    app_user_last_updated = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    app_user_creation = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    app_user_subscription_ref = Column(Integer)
    app_user_email = Column(String(255))
    app_user_login_option = Column(Enum('google', 'gluttex'))

    placed_order = relationship('PlacedOrder', back_populates='ordering_user')
    product = relationship('Product', back_populates='app_user')


class Product(Base):
    __tablename__ = 'product'
    __table_args__ = (
        ForeignKeyConstraint(['product_owner'], ['app_user.id_app_user'], ondelete='RESTRICT', onupdate='RESTRICT', name='fk_product_3'),
        Index('fk_product_3_idx', 'product_owner'),
    )

    id_product = Column(Integer, primary_key=True)
    product_name = Column(String(45))
    product_brand = Column(String(45))
    product_barcode = Column(String(45))
    last_updated = Column(DateTime, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    created = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    product_description = Column(String(300))
    product_price = Column(Float(asdecimal=True), server_default=text("'0'"))
    product_base_price = Column(Float(asdecimal=True), server_default=text("'0'"))
    product_quantity = Column(Integer, server_default=text("'0'"))
    product_reserved_quantity = Column(Integer, server_default=text("'0'"))
    product_quantifier = Column(String(45))
    product_owner = Column(Integer)
    product_visibility = Column(Enum('VISIBLE', 'HIDDEN'), server_default=text("'VISIBLE'"))

    app_user = relationship('AppUser', back_populates='product')
    ordered_item = relationship('OrderedItem', back_populates='ordered_product')
    service_resource_requirement = relationship('ServiceResourceRequirement', back_populates='product')
    product_consumption = relationship('ProductConsumption', back_populates='consumed_product')


class OrderedItem(Base):
    __tablename__ = 'ordered_item'
    __table_args__ = (
        ForeignKeyConstraint(['order_ref'], ['placed_order.id_placed_order'], name='fk_ordered_item_3'),
        ForeignKeyConstraint(['ordered_product_id'], ['product.id_product'], ondelete='RESTRICT', onupdate='RESTRICT', name='fk_ordered_item_1'),
        Index('fk_ordered_item_1_idx', 'ordered_product_id'),
        Index('fk_ordered_item_3_idx', 'order_ref')
    )

    id_ordered_item = Column(Integer, primary_key=True)
    ordered_product_id = Column(Integer)
    ordered_quantity = Column(Integer)
    reserved_quantity = Column(Integer, server_default=text("'0'"))
    applied_vat = Column(Float(asdecimal=True))
    order_ref = Column(Integer)
    unit_price = Column(Float(asdecimal=True))
    product_discount = Column(Float(asdecimal=True))
    ordered_item_delivery_status = Column(Enum('pending', 'processing', 'shipped', 'delivered', 'cancelled', 'returned', 'partial'), server_default=text("'pending'"))
    ordered_item_delivery_fee = Column(Float(asdecimal=True), server_default=text("'0'"))
    ordered_item_last_mod = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    placed_order_creation = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))

    placed_order = relationship('PlacedOrder', back_populates='ordered_item')
    ordered_product = relationship('Product', back_populates='ordered_item')


class OrderedService(Base):
    __tablename__ = 'ordered_service'

    ordered_service_id = Column(Integer, primary_key=True)
    ordered_service_quantity = Column(Integer, server_default=text("'1'"))
    ordered_service_unit_price = Column(DECIMAL(15, 4))
    ordered_service_total_price = Column(DECIMAL(15, 4))
    ordered_service_notes = Column(Text)
    ordered_service_created_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    ordered_service_updated_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    ordered_service_scheduled_at = Column(TIMESTAMP)

    product_consumption = relationship('ProductConsumption', back_populates='consuming_service')


class ServiceResourceRequirement(Base):
    __tablename__ = 'service_resource_requirement'
    __table_args__ = (
        ForeignKeyConstraint(['service_resource_requirement_product_ref'], ['product.id_product'], name='fk_service_resource_requirement_1'),
        Index('fk_service_resource_requirement_1_idx', 'service_resource_requirement_product_ref'),
        Index('idx_resource_requirement_name', 'service_resource_requirement_name'),
        Index('idx_resource_requirement_type', 'service_resource_requirement_type')
    )

    service_resource_requirement_id = Column(Integer, primary_key=True)
    service_resource_requirement_service_id = Column(Integer)
    service_resource_requirement_name = Column(String(255))
    service_resource_requirement_type = Column(String(100))
    service_resource_requirement_quantity = Column(Integer, server_default=text("'1'"))
    service_resource_requirement_cost_per_unit = Column(DECIMAL(15, 4))
    service_resource_requirement_is_consumable = Column(TINYINT(1), server_default=text("'0'"))
    service_resource_requirement_notes = Column(Text)
    service_resource_requirement_created_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    service_resource_requirement_updated_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    service_resource_requirement_product_ref = Column(Integer)

    product = relationship('Product', back_populates='service_resource_requirement')
    product_consumption = relationship('ProductConsumption', back_populates='service_resource_requirement')


class ProductConsumption(Base):
    __tablename__ = 'product_consumption'
    __table_args__ = (
        ForeignKeyConstraint(['consumed_product_id'], ['product.id_product'], name='fk_product_consumption_product1'),
        ForeignKeyConstraint(['consuming_service_id'], ['ordered_service.ordered_service_id'], name='fk_product_consumption_ordered_service1'),
        ForeignKeyConstraint(['resource_req_ref'], ['service_resource_requirement.service_resource_requirement_id'], name='fk_product_consumption_service_resource_requirement1'),
        Index('fk_product_consumption_ordered_service1_idx', 'consuming_service_id'),
        Index('fk_product_consumption_product1_idx', 'consumed_product_id'),
        Index('fk_product_consumption_service_resource_requirement1_idx', 'resource_req_ref')
    )

    id_product_consumption = Column(Integer, primary_key=True)
    resource_req_ref = Column(Integer)
    consuming_service_id = Column(Integer)
    consumed_product_id = Column(Integer)
    product_reserved_quantity = Column(Integer, server_default=text("'0'"))

    consumed_product = relationship('Product', back_populates='product_consumption')
    consuming_service = relationship('OrderedService', back_populates='product_consumption')
    service_resource_requirement = relationship('ServiceResourceRequirement', back_populates='product_consumption')
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Table,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import enum


class UserRole(str, enum.Enum):
    cliente = "cliente"
    dueno = "dueno"


class OrderStatus(str, enum.Enum):
    en_cola       = "en_cola"
    pendiente     = "pendiente"
    aceptado      = "aceptado"
    en_preparacion = "en_preparacion"
    en_camino     = "en_camino"
    entregado     = "entregado"
    rechazado     = "rechazado"
    devolucion_solicitada = "devolucion_solicitada"
    devolucion_aprobada   = "devolucion_aprobada"


class OrderType(str, enum.Enum):
    pedido     = "pedido"
    devolucion = "devolucion"


class PaymentMethod(str, enum.Enum):
    transferencia = "transferencia"
    yape          = "yape"
    efectivo      = "efectivo"


class PaymentStatus(str, enum.Enum):
    pendiente = "pendiente"
    pagado    = "pagado"
    fallido   = "fallido"


class ReturnStatus(str, enum.Enum):
    solicitada = "solicitada"
    aprobada   = "aprobada"
    rechazada  = "rechazada"


class DeliveryStatus(str, enum.Enum):
    programado = "programado"
    en_camino  = "en_camino"
    completado = "completado"


delivery_orders = Table(
    "delivery_orders",
    Base.metadata,
    Column("delivery_id", Integer, ForeignKey("deliveries.id")),
    Column("order_id",    Integer, ForeignKey("orders.id")),
)


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name          = Column(String(255), nullable=False)
    phone         = Column(String(50))
    address       = Column(Text)
    role          = Column(SAEnum(UserRole), default=UserRole.cliente, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="user", foreign_keys="Order.user_id")
    logs   = relationship("OrderLog", back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String(255), nullable=False)
    weight_range   = Column(String(100))
    presentation   = Column(String(100))
    description    = Column(Text)
    min_qty        = Column(Integer, default=10, nullable=False)
    max_qty        = Column(Integer, default=200, nullable=False)
    price_per_unit = Column(Float, nullable=False)
    badge          = Column(String(50))
    active         = Column(Boolean, default=True, nullable=False)

    order_items = relationship("OrderItem", back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    id                = Column(Integer, primary_key=True, index=True)
    user_id           = Column(Integer, ForeignKey("users.id"), nullable=False)
    status            = Column(SAEnum(OrderStatus), default=OrderStatus.pendiente, nullable=False)
    order_type        = Column(SAEnum(OrderType),  default=OrderType.pedido,     nullable=False)
    original_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    total_amount      = Column(Float, default=0.0, nullable=False)
    payment_method    = Column(SAEnum(PaymentMethod))
    notes             = Column(Text)
    rejection_reason  = Column(Text)
    unique_hash       = Column(String(64), index=True, nullable=True)
    archived          = Column(Boolean, default=False, nullable=False)
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user           = relationship("User", back_populates="orders", foreign_keys=[user_id])
    items          = relationship("OrderItem",  back_populates="order", cascade="all, delete-orphan")
    payment        = relationship("Payment",    back_populates="order", uselist=False, cascade="all, delete-orphan")
    deliveries     = relationship("Delivery",   secondary=delivery_orders, back_populates="orders")
    original_order = relationship("Order", remote_side="Order.id", foreign_keys=[original_order_id])
    logs           = relationship("OrderLog", back_populates="order", foreign_keys="OrderLog.order_id")


class OrderItem(Base):
    __tablename__ = "order_items"

    id         = Column(Integer, primary_key=True, index=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity   = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    subtotal   = Column(Float, nullable=False)

    order   = relationship("Order",   back_populates="items")
    product = relationship("Product", back_populates="order_items")


class Payment(Base):
    __tablename__ = "payments"

    id         = Column(Integer, primary_key=True, index=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    method     = Column(SAEnum(PaymentMethod), nullable=False)
    status     = Column(SAEnum(PaymentStatus), default=PaymentStatus.pendiente)
    amount     = Column(Float, nullable=False)
    reference  = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="payment")


class Delivery(Base):
    __tablename__ = "deliveries"

    id            = Column(Integer, primary_key=True, index=True)
    trip_name     = Column(String(255), nullable=False)
    delivery_date = Column(DateTime, nullable=False)
    zone          = Column(String(255))
    status        = Column(SAEnum(DeliveryStatus), default=DeliveryStatus.programado)
    notes         = Column(Text)
    created_at    = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", secondary=delivery_orders, back_populates="deliveries")


class Return(Base):
    __tablename__ = "returns"

    id                = Column(Integer, primary_key=True, index=True)
    original_order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    new_order_id      = Column(Integer, ForeignKey("orders.id"), nullable=True)
    reason            = Column(Text, nullable=False)
    status            = Column(SAEnum(ReturnStatus), default=ReturnStatus.solicitada)
    created_at        = Column(DateTime, default=datetime.utcnow)


class OrderLog(Base):
    """Audit trail — every status change is recorded here."""
    __tablename__ = "order_logs"

    id          = Column(Integer, primary_key=True, index=True)
    order_id    = Column(Integer, ForeignKey("orders.id"), nullable=False)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    from_status = Column(String(50))
    to_status   = Column(String(50), nullable=False)
    notes       = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="logs", foreign_keys=[order_id])
    user  = relationship("User",  back_populates="logs")


class ChatConversation(Base):
    """One chat session per user (or anonymous)."""
    __tablename__ = "chat_conversations"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=True)
    escalated    = Column(Boolean, default=False, nullable=False)
    escalated_at = Column(DateTime, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    messages = relationship(
        "ChatMessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessageModel.id",
    )
    user = relationship("User", foreign_keys=[user_id])


class ChatMessageModel(Base):
    """Individual message inside a ChatConversation."""
    __tablename__ = "chat_messages"

    id              = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id"), nullable=False)
    role            = Column(String(20), nullable=False)   # "user" | "assistant"
    content         = Column(Text, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("ChatConversation", back_populates="messages")

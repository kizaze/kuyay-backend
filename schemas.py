from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from models import (
    UserRole, OrderStatus, OrderType,
    PaymentMethod, PaymentStatus, ReturnStatus, DeliveryStatus,
)


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    role: UserRole
    created_at: datetime
    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# ── Products ──────────────────────────────────────────────────────────────────

class ProductBase(BaseModel):
    name: str
    weight_range: Optional[str] = None
    presentation: Optional[str] = None
    description: Optional[str] = None
    min_qty: int = 10
    max_qty: int = 200
    price_per_unit: float
    badge: Optional[str] = None
    active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    weight_range: Optional[str] = None
    presentation: Optional[str] = None
    description: Optional[str] = None
    min_qty: Optional[int] = None
    max_qty: Optional[int] = None
    price_per_unit: Optional[float] = None
    badge: Optional[str] = None
    active: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    model_config = {"from_attributes": True}


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    subtotal: float
    product: Optional[ProductResponse] = None
    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    payment_method: PaymentMethod
    notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    notes: Optional[str] = None  # used as rejection_reason when rejecting


class OrderResponse(BaseModel):
    id: int
    user_id: int
    status: OrderStatus
    order_type: OrderType
    original_order_id: Optional[int] = None
    total_amount: float
    payment_method: Optional[PaymentMethod] = None
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    unique_hash: Optional[str] = None
    archived: bool = False
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []
    user: Optional[UserResponse] = None
    model_config = {"from_attributes": True}


# ── Payments ──────────────────────────────────────────────────────────────────

class PaymentUpdate(BaseModel):
    status: PaymentStatus
    reference: Optional[str] = None


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    method: PaymentMethod
    status: PaymentStatus
    amount: float
    reference: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Deliveries ────────────────────────────────────────────────────────────────

class DeliveryCreate(BaseModel):
    trip_name: str
    delivery_date: datetime
    zone: str
    notes: Optional[str] = None
    order_ids: List[int] = []


class DeliveryUpdate(BaseModel):
    trip_name: Optional[str] = None
    delivery_date: Optional[datetime] = None
    zone: Optional[str] = None
    status: Optional[DeliveryStatus] = None
    notes: Optional[str] = None
    order_ids: Optional[List[int]] = None


class DeliveryResponse(BaseModel):
    id: int
    trip_name: str
    delivery_date: datetime
    zone: Optional[str] = None
    status: DeliveryStatus
    notes: Optional[str] = None
    created_at: datetime
    orders: List[OrderResponse] = []
    model_config = {"from_attributes": True}


# ── Returns ───────────────────────────────────────────────────────────────────

class ReturnCreate(BaseModel):
    original_order_id: int
    reason: str


class ReturnResponse(BaseModel):
    id: int
    original_order_id: int
    new_order_id: Optional[int] = None
    reason: str
    status: ReturnStatus
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    order_id: Optional[int] = None
    conversation_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: int
    action: Optional[str] = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    created_at: datetime
    escalated: bool = False
    preview: Optional[str] = None
    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    id: int
    created_at: datetime
    messages: List[ChatMessageOut] = []
    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    orders_today: int
    revenue_today: float
    pending_orders: int
    top_products: List[Any] = []

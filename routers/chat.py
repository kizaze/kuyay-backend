from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from services.agent_service import get_agent_response
from routers.auth import get_current_user
from websocket_manager import ws_manager
from jose import JWTError, jwt
from datetime import datetime
import os
import models
import schemas
from typing import List, Optional

_oauth2_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
_SECRET_KEY = os.getenv("SECRET_KEY", "kuyay-dev-secret-change-in-production")
_ALGORITHM  = "HS256"


def _optional_user(
    token: str = Depends(_oauth2_optional),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not token:
        return None
    try:
        payload  = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        user_id  = int(payload.get("sub"))
        return db.query(models.User).filter(models.User.id == user_id).first()
    except (JWTError, TypeError, ValueError):
        return None


router = APIRouter()

STATUS_LABELS = {
    "pendiente":     "Pendiente de confirmación",
    "aceptado":      "Aceptado — en espera de preparación",
    "en_preparacion":"En preparación",
    "en_camino":     "En camino",
    "entregado":     "Entregado",
    "rechazado":     "Rechazado",
}

PAYMENT_LABELS = {
    "transferencia": "Transferencia bancaria",
    "yape":          "Yape",
    "efectivo":      "Efectivo contra entrega",
}


def _build_order_context(order_id: int, db: Session) -> str:
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return f"No se encontró el pedido #{order_id}."
    status_label  = STATUS_LABELS.get(order.status.value, order.status.value)
    payment_label = PAYMENT_LABELS.get(
        order.payment_method.value if order.payment_method else "", "No especificado"
    )
    items_summary = ", ".join(
        f"{item.quantity} x {item.product.name}"
        for item in order.items if item.product
    )
    return (
        f"Pedido #{order.id}\n"
        f"Estado: {status_label}\n"
        f"Total: S/. {order.total_amount:.2f}\n"
        f"Método de pago: {payment_label}\n"
        f"Productos: {items_summary or 'sin detalle'}\n"
        f"Fecha: {order.created_at.strftime('%d/%m/%Y %H:%M')}"
    )


# ── Main chat endpoint ────────────────────────────────────────────────────────

@router.post("/", response_model=schemas.ChatResponse)
async def chat(
    request: schemas.ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(_optional_user),
):
    order_context = ""
    if request.order_id:
        order_context = _build_order_context(request.order_id, db)

    history = [{"role": m.role, "content": m.content} for m in request.history]
    result  = get_agent_response(request.message, history, order_context)
    reply   = result["reply"]
    action  = result["action"]

    # Persist conversation ─────────────────────────────────────────────────────
    if request.conversation_id:
        conv = db.query(models.ChatConversation).filter(
            models.ChatConversation.id == request.conversation_id
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
    else:
        conv = models.ChatConversation(
            user_id=current_user.id if current_user else None
        )
        db.add(conv)
        db.flush()

    db.add(models.ChatMessageModel(conversation_id=conv.id, role="user",      content=request.message))
    db.add(models.ChatMessageModel(conversation_id=conv.id, role="assistant", content=reply))

    # Auto-escalate when agent signals it ─────────────────────────────────────
    if action == "escalar" and not conv.escalated:
        conv.escalated    = True
        conv.escalated_at = datetime.utcnow()
        user_name = current_user.name if current_user else "Visitante"
        preview   = request.message[:120]
        background_tasks.add_task(ws_manager.send_escalation, conv.id, user_name, preview)

    db.commit()

    return schemas.ChatResponse(reply=reply, conversation_id=conv.id, action=action)


# ── Manual escalation ─────────────────────────────────────────────────────────

@router.post("/conversations/{conv_id}/escalate", status_code=200)
async def escalate_conversation(
    conv_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(_optional_user),
):
    conv = db.query(models.ChatConversation).filter(
        models.ChatConversation.id == conv_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv.escalated    = True
    conv.escalated_at = datetime.utcnow()
    db.commit()

    user_name = current_user.name if current_user else "Visitante"
    last_user_msg = next(
        (m.content for m in reversed(conv.messages) if m.role == "user"), ""
    )
    background_tasks.add_task(
        ws_manager.send_escalation, conv.id, user_name, last_user_msg[:120]
    )
    return {"ok": True, "conversation_id": conv_id}


# ── Conversation history endpoints ────────────────────────────────────────────

@router.get("/conversations", response_model=List[schemas.ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    convs = (
        db.query(models.ChatConversation)
        .filter(models.ChatConversation.user_id == current_user.id)
        .order_by(models.ChatConversation.created_at.desc())
        .all()
    )
    result = []
    for c in convs:
        first   = c.messages[0].content if c.messages else None
        preview = (first[:80] + "…") if first and len(first) > 80 else first
        result.append(schemas.ConversationOut(
            id=c.id, created_at=c.created_at,
            escalated=c.escalated, preview=preview,
        ))
    return result


@router.get("/conversations/{conv_id}", response_model=schemas.ConversationDetail)
def get_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    conv = db.query(models.ChatConversation).filter(
        models.ChatConversation.id == conv_id,
        models.ChatConversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return conv


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    conv = db.query(models.ChatConversation).filter(
        models.ChatConversation.id == conv_id,
        models.ChatConversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    db.delete(conv)
    db.commit()

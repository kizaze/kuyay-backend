from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine, SessionLocal
from routers import auth, products, orders, payments, deliveries, returns, chat
from routers import admin as admin_router
from websocket_manager import ws_manager
import models


def seed_products(db):
    if db.query(models.Product).count() > 0:
        return
    catalog = [
        {
            "name": "Cuy grande fresco",
            "weight_range": "800g – 1 kg",
            "presentation": "fresco",
            "description": "Eviscerado y pelado el mismo día. Ideal para cuy al horno, chactado o frito.",
            "price_per_unit": 35.0,
            "badge": None,
        },
        {
            "name": "Cuy grande al vacío",
            "weight_range": "800g – 1 kg sellado al vacío",
            "presentation": "vacio",
            "description": "Vida útil extendida. Sellado al vacío con cadena de frío. Perfecto para restaurantes.",
            "price_per_unit": 42.0,
            "badge": "NUEVO",
        },
        {
            "name": "Cuy mediano fresco",
            "weight_range": "500g – 700g",
            "presentation": "fresco",
            "description": "Porciones individuales perfectas para preparaciones rápidas.",
            "price_per_unit": 25.0,
            "badge": None,
        },
        {
            "name": "Cuy mediano al vacío",
            "weight_range": "500g – 700g sellado al vacío",
            "presentation": "vacio",
            "description": "Para quienes prefieren comprar en cantidad y mantener stock.",
            "price_per_unit": 30.0,
            "badge": None,
        },
        {
            "name": "Cuy deshuesado",
            "weight_range": "Especial · Sin hueso",
            "presentation": "deshuesado",
            "description": "Listo para rellenos, enrollados y preparaciones gourmet.",
            "price_per_unit": 55.0,
            "badge": "CHEF",
        },
        {
            "name": "Cuy grande trozado",
            "weight_range": "Grande · Trozado x4",
            "presentation": "trozado",
            "description": "Cortado en 4 presas iguales. Listo para la olla o la parrilla.",
            "price_per_unit": 38.0,
            "badge": None,
        },
    ]
    for p in catalog:
        db.add(models.Product(min_qty=10, max_qty=200, active=True, **p))
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_products(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Kuyay API",
    version="2.0.0",
    description="Sistema de catálogo y pedidos — El Rincón del Príncipe",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,              prefix="/auth",        tags=["Auth"])
app.include_router(products.router,          prefix="/products",    tags=["Productos"])
app.include_router(orders.router,            prefix="/orders",      tags=["Pedidos"])
app.include_router(payments.router,          prefix="/payments",    tags=["Pagos"])
app.include_router(deliveries.router,        prefix="/deliveries",  tags=["Despachos"])
app.include_router(returns.router,           prefix="/returns",     tags=["Devoluciones"])
app.include_router(chat.router,              prefix="/chat",        tags=["Chat"])
app.include_router(admin_router.router,      prefix="/admin",       tags=["Admin"])


@app.websocket("/ws/admin")
async def websocket_admin(websocket: WebSocket):
    """Real-time admin notifications channel."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; admin client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


@app.get("/")
def root():
    return {"app": "Kuyay", "version": "2.0.0", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}

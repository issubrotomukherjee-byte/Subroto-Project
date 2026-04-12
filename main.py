from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import engine
from database.base import Base
from routes import medicine, inventory, billing, store as store_routes, customer, loyalty

# Import every model so Base.metadata knows about all tables
from models import (  # noqa: F401
    store as store_model,
    medicine as med_model,
    inventory as inv_model,
    customer as customer_model,
    order,
    order_item,
    order_item_batch,
    customer_loyalty,
    loyalty_transaction,
)

# Create all database tables
# NOTE: create_all() only creates NEW tables. It does NOT update existing
# tables when you add/remove columns. If you change a model, reset the DB:
#   1. Stop the server
#   2. Run: rm neomeds.db
#   3. Restart: uvicorn main:app --reload
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NeoMeds POS",
    description="Pharmacy Point-of-Sale System",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Register route modules
app.include_router(medicine.router, prefix="/api/medicines", tags=["Medicines"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(billing.router, prefix="/api/orders", tags=["Orders"])
app.include_router(store_routes.router, prefix="/api/stores", tags=["Stores"])
app.include_router(customer.router, prefix="/api/customers", tags=["Customers"])
app.include_router(loyalty.router, prefix="/api/loyalty", tags=["Loyalty"])


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "app": "NeoMeds POS"}

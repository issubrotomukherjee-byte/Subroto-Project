from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
from models.customer import Customer
from models.order import Order
from models.order_item import OrderItem
from models.medicine import Medicine
from schemas.customer_schema import CustomerCreate


def create_customer(db: Session, data: CustomerCreate):
    """Create a new customer."""
    customer = Customer(name=data.name, phone=data.phone, email=data.email)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def list_customers(db: Session):
    """Return all customers."""
    return db.query(Customer).all()


def get_customer(db: Session, customer_id: int):
    """Return a single customer by ID."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def get_customer_orders(db: Session, customer_id: int):
    """Return all orders for a customer, with item details."""
    customer = get_customer(db, customer_id)

    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .all()
    )

    order_list = []
    for order in orders:
        items = []
        for item in order.items:
            medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
            items.append({
                "medicine_id": item.medicine_id,
                "medicine_name": medicine.name if medicine else "Unknown",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
            })
        order_list.append({
            "order_id": order.id,
            "store_id": order.store_id,
            "total_amount": order.total_amount,
            "created_at": order.created_at,
            "items": items,
        })

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "orders": order_list,
    }


def get_customer_medicines(db: Session, customer_id: int):
    """Return distinct medicines purchased by a customer with totals."""
    customer = get_customer(db, customer_id)

    results = (
        db.query(
            OrderItem.medicine_id,
            Medicine.name.label("medicine_name"),
            func.sum(OrderItem.quantity).label("total_quantity"),
            func.sum(OrderItem.subtotal).label("total_spent"),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .join(Medicine, OrderItem.medicine_id == Medicine.id)
        .filter(Order.customer_id == customer_id)
        .group_by(OrderItem.medicine_id, Medicine.name)
        .all()
    )

    medicines = [
        {
            "medicine_id": row.medicine_id,
            "medicine_name": row.medicine_name,
            "total_quantity": row.total_quantity,
            "total_spent": row.total_spent,
        }
        for row in results
    ]

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "medicines": medicines,
    }

from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database.base import Base


class OrderItemBatch(Base):
    """Tracks exactly which inventory batch(es) were consumed for each order item.

    When an order item's quantity spans multiple batches (FEFO split),
    one row is created per batch used.  This enables:
      - Accurate return processing  (know which batch to restock)
      - Full audit trail             (who got which expiry)
    """
    __tablename__ = "order_item_batches"

    id = Column(Integer, primary_key=True, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

    order_item = relationship("OrderItem", back_populates="batches")
    inventory = relationship("Inventory")

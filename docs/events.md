# Domain Events Catalog

## Event Processing Model

```
Service.method()
    ↓
OutboxStore.append(Event)
    ↓
event_outbox row (same DB transaction)
    ↓
commit
    ↓
OutboxWorker (async polling)
    ↓
Handler(s)
```

### Delivery Semantics

- Events are persisted in the **same database transaction** as domain data.
- Delivery is **asynchronous** — the OutboxWorker polls `event_outbox` every 2 seconds.
- Delivery is **at-least-once** — a handler may be called more than once.
- **Consumers must be idempotent** — duplicate events must be safe.
- Event ordering is **guaranteed only within a single outbox row lifecycle** — cross-event ordering is not guaranteed.

---

## Event Versioning Policy

- All events start at **Version 1**.
- Adding optional fields does **not** require a new version.
- Removing fields or changing semantics **does** require a new version.
- The `event_name` stored in `event_outbox` matches the class name and is the routing key for the OutboxWorker.
- When versioning is needed, the naming convention is: `EventName.v2`.

---

## Summary Table

| Event | Producer | Current Consumers |
|---|---|---|
| ProductCreated | CatalogService.create_product | pricing, inventory |
| ProductUpdated | CatalogService.update_product | — |
| ProductDeleted | CatalogService.delete_product | — |
| CategoryCreated | CatalogService.create_category | — |
| CategoryUpdated | CatalogService.update_category | — |
| CategoryDeleted | CatalogService.delete_category | — |
| StockChanged | InventoryService.adjust_quantity, .commit_sale | — |
| PriceChanged | PricingService.update_price | — |
| OrderCreated | OrderService.create_order | handle_order_created |
| OrderConfirmed | OrderService.confirm_order | — |
| OrderCancelled | OrderService.cancel_order | — |
| OrderStatusChanged | OrderService.transition_status | — |
| PaymentCreated | PaymentService.create_payment | — |
| PaymentSucceeded | PaymentService.confirm_payment | — |
| PaymentFailed | PaymentService.fail_payment | — |
| PaymentRefunded | PaymentService.refund_payment | — |

---

## Event Ownership Matrix

| Domain | Produces | Consumes |
|---|---|---|
| Catalog | ProductCreated, ProductUpdated, ProductDeleted, CategoryCreated, CategoryUpdated, CategoryDeleted | — |
| Pricing | PriceChanged | ProductCreated |
| Inventory | StockChanged | ProductCreated, OrderCreated |
| Orders | OrderCreated, OrderConfirmed, OrderCancelled, OrderStatusChanged | — |
| Payments | PaymentCreated, PaymentSucceeded, PaymentFailed, PaymentRefunded | — |

---

## Event Definitions

Ordered by production flow dependency.

---

### 1. ProductCreated

#### Metadata

- Event Name (stored): ProductCreated
- Version: 1
- Domain: Catalog

#### Producer

CatalogService.create_product

#### Current Consumers

| Consumer | Type |
|---|---|
| pricing.handle_product_created | Projection |
| inventory.handle_product_created | Projection |

#### Potential Future Consumers

- Audit Log

#### Payload

| Field | Type | Notes |
|---|---|---|
| product_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| name | str | |
| price | str | Decimal serialized as string |
| compare_at_price | str | None |
| sku | str | None |
| quantity | int | |

#### Transactional Boundary

- `Product` row + `EventOutbox` row committed atomically in the same transaction.

#### Invariants

- Product row exists in DB before the event is emitted.
- Pricing and Inventory rows do NOT exist yet — they are created by the consumers.
- `name` matches the product name (used for snapshot cache in orders).

#### Idempotency

Consumers use `find_one(product_id=..., tenant_id=...)` before creating rows. If the row already exists, they skip creation. This makes them safe against duplicate event delivery.

#### Retry Behavior

- Processed by OutboxWorker.
- Failed handlers increment `retry_count` on the outbox row.
- Worker retries with exponential backoff (`2^retry_count` seconds, max 1 hour).
- After `max_retries` (5), the event is marked `FAILED`.

#### Failure Semantics

- Pricing and Inventory handlers are independent — failure in one does NOT prevent the other.
- If both handlers succeed, the outbox row is marked `COMPLETED`.
- If either handler fails, the row stays in retry flow.

#### Event Flow

```
CatalogService.create_product()
    ↓
OutboxStore.append(ProductCreated)
    ↓
[Product row] + [EventOutbox row] committed atomically
    ↓
OutboxWorker polls event_outbox
    ↓
pricing.handle_product_created() → creates ProductPricing row
    ↓
inventory.handle_product_created() → creates ProductInventory row
    ↓
EventOutbox.status = COMPLETED
```

---

### 2. ProductUpdated

#### Metadata

- Event Name (stored): ProductUpdated
- Version: 1
- Domain: Catalog

#### Producer

CatalogService.update_product

#### Current Consumers

None

#### Potential Future Consumers

- Search index sync
- Analytics

#### Payload

| Field | Type | Notes |
|---|---|---|
| product_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| name | str | |
| price | str | None; Decimal serialized as string |

#### Transactional Boundary

- `Product` row update + `EventOutbox` row committed atomically.

#### Invariants

- Product row exists and is not soft-deleted.
- `name` and `price` reflect the new values (not the old ones).

#### Idempotency

No consumers currently — idempotency not required.

#### Retry Behavior

Standard outbox retry (see Event Processing Model).

#### Failure Semantics

No consumers — event is purely informational.

#### Event Flow

```
CatalogService.update_product()
    ↓
OutboxStore.append(ProductUpdated)
    ↓
[Product update] + [EventOutbox row] committed atomically
    ↓
(no consumers currently)
```

---

### 3. ProductDeleted

#### Metadata

- Event Name (stored): ProductDeleted
- Version: 1
- Domain: Catalog

#### Producer

CatalogService.delete_product

#### Current Consumers

None

#### Potential Future Consumers

- Search index removal
- Analytics
- Cascade cleanup

#### Payload

| Field | Type | Notes |
|---|---|---|
| product_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |

#### Transactional Boundary

- `Product.deleted_at` (soft delete) + `EventOutbox` row committed atomically.

#### Invariants

- Product is soft-deleted (not hard-deleted from DB).

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers.

#### Event Flow

```
CatalogService.delete_product()
    ↓
OutboxStore.append(ProductDeleted)
    ↓
[soft delete] + [EventOutbox row] committed atomically
```

---

### 4. CategoryCreated

#### Metadata

- Event Name (stored): CategoryCreated
- Version: 1
- Domain: Catalog

#### Producer

CatalogService.create_category

#### Current Consumers

None

#### Potential Future Consumers

- Category feed
- Navigation sync

#### Payload

| Field | Type | Notes |
|---|---|---|
| category_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| name | str | |

#### Transactional Boundary

- `Category` row + `EventOutbox` row committed atomically.

#### Invariants

- Category row exists in DB.
- If `parent_id` was provided, parent category exists.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers.

#### Event Flow

```
CatalogService.create_category()
    ↓
OutboxStore.append(CategoryCreated)
    ↓
commit
```

---

### 5. CategoryUpdated

#### Metadata

- Event Name (stored): CategoryUpdated
- Version: 1
- Domain: Catalog

#### Producer

CatalogService.update_category

#### Current Consumers

None

#### Potential Future Consumers

- Navigation sync
- SEO cache invalidation

#### Payload

| Field | Type | Notes |
|---|---|---|
| category_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| name | str | |

#### Transactional Boundary

- `Category` row update + `EventOutbox` row committed atomically.

#### Invariants

- Category row exists and is not soft-deleted.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers.

#### Event Flow

```
CatalogService.update_category()
    ↓
OutboxStore.append(CategoryUpdated)
    ↓
commit
```

---

### 6. CategoryDeleted

#### Metadata

- Event Name (stored): CategoryDeleted
- Version: 1
- Domain: Catalog

#### Producer

CatalogService.delete_category

#### Current Consumers

None

#### Potential Future Consumers

- Cascade product uncategorization
- Navigation rebuild

#### Payload

| Field | Type | Notes |
|---|---|---|
| category_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |

#### Transactional Boundary

- `Category.deleted_at` (soft delete) + `EventOutbox` row committed atomically.

#### Invariants

- Category is soft-deleted.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers.

#### Event Flow

```
CatalogService.delete_category()
    ↓
OutboxStore.append(CategoryDeleted)
    ↓
commit
```

---

### 7. StockChanged

#### Metadata

- Event Name (stored): StockChanged
- Version: 1
- Domain: Inventory

#### Producer

- InventoryService.adjust_quantity
- InventoryService.commit_sale

#### Current Consumers

None

#### Potential Future Consumers

- Low stock alert
- Inventory sync with ERP
- Analytics

#### Payload

| Field | Type | Notes |
|---|---|---|
| product_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| old_quantity | int | |
| new_quantity | int | |
| reason | str | "adjustment" or "sale" |

#### Transactional Boundary

- `ProductInventory` update + `InventoryTransaction` row + `EventOutbox` row committed atomically (caller's UoW).

#### Invariants

- `new_quantity` >= 0 after a sale.
- `reserved_quantity` is adjusted before quantity in sale flow.

#### Idempotency

No consumers currently. The producer itself uses idempotency keys for reserve/commit/release operations.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently. Event is purely informational.

#### Event Flow

```
InventoryService.adjust_quantity() / .commit_sale()
    ↓
OutboxStore.append(StockChanged)
    ↓
caller commits (same UoW)
```

---

### 8. PriceChanged

#### Metadata

- Event Name (stored): PriceChanged
- Version: 1
- Domain: Pricing

#### Producer

PricingService.update_price

#### Current Consumers

None

#### Potential Future Consumers

- Price history
- Analytics
- Pricing rule re-evaluation

#### Payload

| Field | Type | Notes |
|---|---|---|
| product_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| old_price | str | Decimal serialized as string |
| new_price | str | Decimal serialized as string |

#### Transactional Boundary

- `ProductPricing` update + `EventOutbox` row committed atomically (caller's UoW).

#### Invariants

- Pricing row exists before and after update.
- `old_price` and `new_price` reflect the actual before/after values.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
PricingService.update_price()
    ↓
OutboxStore.append(PriceChanged)
    ↓
caller commits (same UoW)
```

---

### 9. OrderCreated

#### Metadata

- Event Name (stored): OrderCreated
- Version: 1
- Domain: Orders

#### Producer

OrderService.create_order

#### Current Consumers

| Consumer | Type |
|---|---|
| handle_order_created | Projection (cross-domain side effects) |

#### Potential Future Consumers

- Notification Service
- Analytics

#### Payload

| Field | Type | Notes |
|---|---|---|
| order_id | UUID | |
| user_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| items | list[dict] | `[{"product_id": str, "quantity": int}]` |
| currency | str | default "USD" |
| notes | str | None |

#### Transactional Boundary

- `Order` row + `OrderItem` rows + `EventOutbox` row committed atomically.

#### Invariants

- Order status is `PENDING`.
- Order has at least one item.
- Product snapshots, pricing snapshots, and inventory snapshots were read before order creation (read model, not transactional).
- Total amount equals sum of item subtotals (no tax/discount applied yet).

#### Idempotency

- Order creation itself uses `idempotency_key` — if the same key is used, the existing order is returned (no duplicate).
- The handler `handle_order_created` uses idempotency keys for inventory reservation (`order_{order_id}_{product_id}`) — if reservation already exists, it skips.

#### Retry Behavior

Standard outbox retry with exponential backoff. The handler checks order status at the start — if already CONFIRMED/CANCELLED, it skips processing (safe retry).

#### Failure Semantics

- If inventory reservation fails for any item, the order is transitioned to `CANCELLED`.
- If all reservations succeed, the order is transitioned to `CONFIRMED`.
- The handler is **all-or-nothing within a single UoW** — inventory reservations and order status change share one transaction.
- If the handler itself crashes (not a business failure), the outbox row stays in retry. The handler will check `order.status` and skip if already processed (idempotent).

#### Event Flow

```
OrderService.create_order()
    ↓
OutboxStore.append(OrderCreated)
    ↓
[Order row] + [OrderItem rows] + [EventOutbox row] committed atomically
    ↓
OutboxWorker polls event_outbox
    ↓
handle_order_created()
    ├── load order (refresh)
    ├── if status != PENDING → skip
    ├── for each item:
    │   └── InventoryService.reserve(product_id, quantity, idempotency_key)
    ├── if all succeeded → OrderStateMachine.transition(order, CONFIRMED)
    └── if any failed → OrderStateMachine.transition(order, CANCELLED)
    ↓
    commit
```

---

### 10. OrderConfirmed

#### Metadata

- Event Name (stored): OrderConfirmed
- Version: 1
- Domain: Orders

#### Producer

OrderService.confirm_order

#### Current Consumers

None

#### Potential Future Consumers

- Notification Service
- Shipping trigger
- Billing

#### Payload

| Field | Type | Notes |
|---|---|---|
| order_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |

#### Transactional Boundary

- `Order` status update + `EventOutbox` row committed atomically.

#### Invariants

- Order status transitioned from `PENDING` to `CONFIRMED` (validated by state machine).

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
OrderService.confirm_order()
    ↓
OutboxStore.append(OrderConfirmed)
    ↓
[Order status update] + [EventOutbox row] committed atomically
```

---

### 11. OrderCancelled

#### Metadata

- Event Name (stored): OrderCancelled
- Version: 1
- Domain: Orders

#### Producer

OrderService.cancel_order

#### Current Consumers

None

#### Potential Future Consumers

- Notification Service
- Inventory release
- Refund trigger

#### Payload

| Field | Type | Notes |
|---|---|---|
| order_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| reason | str | None |

#### Transactional Boundary

- `Order` status update + `EventOutbox` row committed atomically.

#### Invariants

- Order status transitioned to `CANCELLED` (validated by state machine).
- Once cancelled, no further transitions are allowed.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
OrderService.cancel_order()
    ↓
OutboxStore.append(OrderCancelled)
    ↓
[Order status update] + [EventOutbox row] committed atomically
```

---

### 12. OrderStatusChanged

#### Metadata

- Event Name (stored): OrderStatusChanged
- Version: 1
- Domain: Orders

#### Producer

OrderService.transition_status

#### Current Consumers

None

#### Potential Future Consumers

- Notification Service
- Analytics
- Audit log

#### Payload

| Field | Type | Notes |
|---|---|---|
| order_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| old_status | str | previous status value |
| new_status | str | new status value |

#### Transactional Boundary

- `Order` status update + `EventOutbox` row committed atomically.

#### Invariants

- Status transition is valid according to `OrderStateMachine.TRANSITIONS`.
- `old_status` != `new_status`.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
OrderService.transition_status()
    ↓
OutboxStore.append(OrderStatusChanged)
    ↓
[Order status update] + [EventOutbox row] committed atomically
```

---

### 13. PaymentCreated

#### Metadata

- Event Name (stored): PaymentCreated
- Version: 1
- Domain: Payments

#### Producer

PaymentService.create_payment

#### Current Consumers

None

#### Potential Future Consumers

- Notification Service
- Billing

#### Payload

| Field | Type | Notes |
|---|---|---|
| payment_id | UUID | |
| order_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| amount | Decimal | |
| currency | str | |

#### Transactional Boundary

- `Payment` row + `EventOutbox` row committed atomically.

#### Invariants

- Payment status is `PENDING`.
- Order does not have any other active payment (PENDING or AUTHORIZED).
- `idempotency_key` uniqueness is enforced at DB level (`UniqueConstraint("tenant_id", "idempotency_key")`).

#### Idempotency

- `PaymentService.create_payment` uses `idempotency_key` — if the same key is used, the existing payment is returned.
- DB unique constraint provides a second line of defense.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
PaymentService.create_payment()
    ↓
OutboxStore.append(PaymentCreated)
    ↓
[Payment row] + [EventOutbox row] committed atomically
```

---

### 14. PaymentSucceeded

#### Metadata

- Event Name (stored): PaymentSucceeded
- Version: 1
- Domain: Payments

#### Producer

PaymentService.confirm_payment

#### Current Consumers

None

#### Potential Future Consumers

- Notification Service
- Order fulfillment trigger
- Billing

#### Payload

| Field | Type | Notes |
|---|---|---|
| payment_id | UUID | |
| order_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| provider_reference | str | None; e.g. Stripe PI ID |

#### Transactional Boundary

- `Payment` status update (to PAID) + `EventOutbox` row committed atomically.

#### Invariants

- Payment status transitioned from PENDING/AUTHORIZED to PAID (validated by state machine).
- `provider_reference` is set before commit.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
PaymentService.confirm_payment()
    ↓
OutboxStore.append(PaymentSucceeded)
    ↓
[Payment status update] + [EventOutbox row] committed atomically
```

---

### 15. PaymentFailed

#### Metadata

- Event Name (stored): PaymentFailed
- Version: 1
- Domain: Payments

#### Producer

PaymentService.fail_payment

#### Current Consumers

None

#### Potential Future Consumers

- Notification Service
- Order cancellation trigger

#### Payload

| Field | Type | Notes |
|---|---|---|
| payment_id | UUID | |
| order_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| reason | str | None; failure reason |

#### Transactional Boundary

- `Payment` status update (to FAILED) + `EventOutbox` row committed atomically.

#### Invariants

- Payment status transitioned from PENDING/AUTHORIZED to FAILED (validated by state machine).
- `failure_reason` is set on the Payment model before commit.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
PaymentService.fail_payment()
    ↓
OutboxStore.append(PaymentFailed)
    ↓
[Payment status update] + [EventOutbox row] committed atomically
```

---

### 16. PaymentRefunded

#### Metadata

- Event Name (stored): PaymentRefunded
- Version: 1
- Domain: Payments

#### Producer

PaymentService.refund_payment

#### Current Consumers

None

#### Potential Future Consumers

- Notification Service
- Billing

#### Payload

| Field | Type | Notes |
|---|---|---|
| payment_id | UUID | |
| order_id | UUID | |
| tenant_id | UUID | inherited from DomainEvent |
| reason | str | None |

#### Transactional Boundary

- `Payment` status update (to REFUNDED) + `EventOutbox` row committed atomically.

#### Invariants

- Payment status transitioned from PAID to REFUNDED (validated by state machine).
- A payment cannot be refunded unless it was first marked PAID.

#### Idempotency

No consumers currently.

#### Retry Behavior

Standard outbox retry.

#### Failure Semantics

No consumers currently.

#### Event Flow

```
PaymentService.refund_payment()
    ↓
OutboxStore.append(PaymentRefunded)
    ↓
[Payment status update] + [EventOutbox row] committed atomically
```

---

## Validated Flows

| Event | Validated On | Result |
|---|---|---|
| ProductCreated | (pending) | — |
| OrderCreated | (pending) | — |

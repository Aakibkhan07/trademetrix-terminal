-- Reconciliation state for orders whose broker response was lost.
--
-- An order whose `POST /v2/orders` response never arrived has no `broker_order_id`. The
-- existing reconciliation loop selects on `broker_order_id`, so such an order was invisible
-- to it and stayed unresolved forever. These columns let it be found, counted, and -- when
-- the broker definitively reports no matching order -- retried under explicit policy instead
-- of being requeued blindly.
--
-- Idempotent. All columns are nullable or defaulted, so existing rows load unchanged.

ALTER TABLE public.oms_orders
    ADD COLUMN IF NOT EXISTS reconcile_attempts     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS not_found_observations INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS intent_fingerprint     TEXT;

COMMENT ON COLUMN public.oms_orders.reconcile_attempts IS
    'How many times reconciliation has asked the broker about this order.';
COMMENT ON COLUMN public.oms_orders.not_found_observations IS
    'Consecutive "broker does not hold it" answers. A single absence is not proof of absence.';
COMMENT ON COLUMN public.oms_orders.intent_fingerprint IS
    'Hash of the material order attributes. A retry presenting a different fingerprint is a '
    'NEW order and must pass complete risk evaluation; an identical one is a transport retry.';

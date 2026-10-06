-- Make the OMS columns this series added match the model's own typing.
--
-- `OmniOrder` declares these as non-optional (`instrument_type: str = ""`,
-- `disclosed_quantity: int = 0`, ...), but the two migrations that added them created
-- nullable columns with no default. So a row written before the column existed reads back as
-- NULL, pydantic rejects NULL for `str`/`int`, and `load_order` raises. Measured in
-- production logs on startup:
--
--   WARNING oms.manager Failed to recover order <id>: OmniOrder
--   intent_fingerprint  Input should be a valid string [input_value=None]
--
-- Startup recovery therefore skipped every such row -- silently, at WARNING level, after
-- logging a count of what it did recover. A database that disagrees with the model it is
-- read into is a latent outage, not a cosmetic mismatch.
--
-- Idempotent. Backfills NULL first, then sets the default and NOT NULL, in that order, so
-- the constraint can be applied to existing rows.

UPDATE public.oms_orders SET
    instrument_type     = COALESCE(instrument_type, ''),
    expiry_date         = COALESCE(expiry_date, ''),
    strike_price        = COALESCE(strike_price, 0),
    option_type         = COALESCE(option_type, ''),
    validity            = COALESCE(validity, ''),
    disclosed_quantity  = COALESCE(disclosed_quantity, 0),
    intent_fingerprint  = COALESCE(intent_fingerprint, ''),
    reconcile_attempts  = COALESCE(reconcile_attempts, 0),
    not_found_observations = COALESCE(not_found_observations, 0)
WHERE instrument_type IS NULL
   OR expiry_date IS NULL
   OR strike_price IS NULL
   OR option_type IS NULL
   OR validity IS NULL
   OR disclosed_quantity IS NULL
   OR intent_fingerprint IS NULL
   OR reconcile_attempts IS NULL
   OR not_found_observations IS NULL;

ALTER TABLE public.oms_orders
    ALTER COLUMN instrument_type        SET DEFAULT '',
    ALTER COLUMN expiry_date            SET DEFAULT '',
    ALTER COLUMN strike_price           SET DEFAULT 0,
    ALTER COLUMN option_type            SET DEFAULT '',
    ALTER COLUMN validity               SET DEFAULT '',
    ALTER COLUMN disclosed_quantity     SET DEFAULT 0,
    ALTER COLUMN intent_fingerprint     SET DEFAULT '',
    ALTER COLUMN reconcile_attempts     SET DEFAULT 0,
    ALTER COLUMN not_found_observations SET DEFAULT 0,
    ALTER COLUMN instrument_type        SET NOT NULL,
    ALTER COLUMN expiry_date            SET NOT NULL,
    ALTER COLUMN option_type            SET NOT NULL,
    ALTER COLUMN validity               SET NOT NULL,
    ALTER COLUMN disclosed_quantity     SET NOT NULL,
    ALTER COLUMN intent_fingerprint     SET NOT NULL,
    ALTER COLUMN reconcile_attempts     SET NOT NULL,
    ALTER COLUMN not_found_observations SET NOT NULL;

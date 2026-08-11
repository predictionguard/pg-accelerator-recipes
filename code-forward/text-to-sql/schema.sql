-- Example schema — replace with your pod's real tables.
-- The model only sees what you show it here, so keep this in sync with reality.

CREATE TABLE shipments (
    id SERIAL PRIMARY KEY,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    shipped_at DATE NOT NULL,
    destination TEXT
);

CREATE TABLE inventory (
    sku TEXT PRIMARY KEY,
    description TEXT,
    quantity_on_hand INTEGER NOT NULL,
    warehouse TEXT
);

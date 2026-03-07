-- DB Bus Bot — PostgreSQL Schema
-- Run once: psql $DATABASE_URL -f db/schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── ENUMS ───────────────────────────────────────────────────────────────────

CREATE TYPE order_status AS ENUM (
    'WAITING_PAYMENT', 'PAID', 'CLAIMED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'
);
CREATE TYPE order_priority AS ENUM ('STANDARD', 'FAST_TRACK');
CREATE TYPE order_payment_method AS ENUM ('BALANCE', 'DIRECT');
CREATE TYPE deposit_status AS ENUM ('WAITING_DEPOSIT', 'CONFIRMED', 'EXPIRED');
CREATE TYPE ledger_type AS ENUM ('CREDIT', 'DEBIT');
CREATE TYPE ticket_status AS ENUM ('OPEN', 'CLOSED');
CREATE TYPE message_role AS ENUM ('USER', 'ADMIN');
CREATE TYPE admin_role AS ENUM ('agent', 'superadmin');

-- ─── ADMINS (before orders due to FK) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admins (
    id          SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username    TEXT,
    role        admin_role NOT NULL DEFAULT 'agent',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── USERS ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    username        TEXT,
    balance_sol     NUMERIC(18, 9) NOT NULL DEFAULT 0,
    wallet_pubkey   TEXT,
    is_blocked      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── SERVICES ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS services (
    id                   SERIAL PRIMARY KEY,
    name                 TEXT NOT NULL,
    description          TEXT,
    price                NUMERIC(18, 9) NOT NULL,
    eta                  TEXT NOT NULL,
    fast_track_price     NUMERIC(18, 9),
    fast_track_eta       TEXT,
    required_inputs_json JSONB NOT NULL DEFAULT '[]',
    -- Each element: {"field":"x","label":"X","type":"text|url|number|file","required":true}
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── ORDERS ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    service_id          INTEGER NOT NULL REFERENCES services(id),
    status              order_status NOT NULL DEFAULT 'WAITING_PAYMENT',
    priority            order_priority NOT NULL DEFAULT 'STANDARD',
    payment_method      order_payment_method,
    price               NUMERIC(18, 9) NOT NULL,
    eta                 TEXT NOT NULL,
    user_details_json   JSONB NOT NULL DEFAULT '{}',
    pay_address         TEXT,
    pay_memo            TEXT,
    payment_expires_at  TIMESTAMPTZ,
    payment_tx_sig      TEXT,
    paid_at             TIMESTAMPTZ,
    progress            INTEGER NOT NULL DEFAULT 0,
    progress_stage      TEXT NOT NULL DEFAULT 'queued',
    proof_json          JSONB,
    admin_notes         TEXT,
    claimed_by          INTEGER REFERENCES admins(id),
    claimed_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── DEPOSITS ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deposits (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    expected_amount NUMERIC(18, 9) NOT NULL,
    address         TEXT NOT NULL,
    memo            TEXT,
    status          deposit_status NOT NULL DEFAULT 'WAITING_DEPOSIT',
    expires_at      TIMESTAMPTZ NOT NULL,
    confirmed_tx    TEXT,
    confirmed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── LEDGER ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ledger (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    type        ledger_type NOT NULL,
    amount      NUMERIC(18, 9) NOT NULL,
    reason      TEXT NOT NULL,
    ref_id      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── TICKETS ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickets (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    order_id    INTEGER REFERENCES orders(id),
    status      ticket_status NOT NULL DEFAULT 'OPEN',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id          SERIAL PRIMARY KEY,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    from_role   message_role NOT NULL,
    text        TEXT,
    file_ref    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── AUDIT LOG ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id          SERIAL PRIMARY KEY,
    admin_id    INTEGER REFERENCES admins(id),
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   INTEGER,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_orders_user_id       ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status        ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_claimed_by    ON orders(claimed_by);
CREATE INDEX IF NOT EXISTS idx_deposits_user_id     ON deposits(user_id);
CREATE INDEX IF NOT EXISTS idx_deposits_status      ON deposits(status);
CREATE INDEX IF NOT EXISTS idx_ledger_user_id       ON ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_user_id      ON tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status       ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_ticket_messages_tid  ON ticket_messages(ticket_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_admin     ON audit_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity    ON audit_logs(entity, entity_id);

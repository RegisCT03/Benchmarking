CREATE TABLE IF NOT EXISTS registros_academicos (
    id UUID PRIMARY KEY,
    data JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_registros_fecha 
ON registros_academicos USING BTREE (((data->>'fecha_registro')::timestamptz));

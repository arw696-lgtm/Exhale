-- =============================================================================
-- Exhale — Relational Storage Schema (Blueprint §5.3, §4)
-- Zero-Knowledge Core: the persistence engine stores only encrypted payloads,
-- nonces, and KEK-wrapped tokens. Cloud operators have zero plaintext
-- observability into personal identities. Queries use blind indexes.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Households (tenancy root)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS families (
    family_id       VARCHAR(64) PRIMARY KEY,
    display_label   VARCHAR(128),
    -- KEK is derived client-side (PBKDF2) and never stored in plaintext.
    -- We persist only the salt + a verification tag to validate the passphrase.
    kek_salt        BYTEA        NOT NULL,
    kek_verify_tag  VARCHAR(64)  NOT NULL,

    -- Encrypted household profile (parent name, preferences) — same envelope
    -- layout as node payloads. Nullable: a family may have no profile yet.
    encrypted_profile_blob  TEXT,
    profile_nonce           VARCHAR(24),
    profile_tag             VARCHAR(32),
    profile_wrapped_dek     VARCHAR(96),

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- End-to-end encrypted graph NODES (Blueprint §5.3 verbatim contract)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS family_secure_nodes (
    node_id                 VARCHAR(64) PRIMARY KEY,
    family_id               VARCHAR(64) NOT NULL,

    -- Non-sensitive routing type kept in cleartext so the engine can traverse
    -- the graph shape (PERSON/EVENT/OBLIGATION...) without decrypting payloads.
    node_type               VARCHAR(32) NOT NULL,

    -- Cryptographic Blind Index for query evaluations without data leakage.
    blind_index_hash        CHAR(64)    NOT NULL,

    -- Encrypted payload block containing demographic and relational values.
    encrypted_payload_blob  TEXT        NOT NULL,

    -- AES-GCM Initialization Vector and MAC verification token.
    cryptographic_nonce     VARCHAR(24) NOT NULL,
    key_verification_tag    VARCHAR(32) NOT NULL,

    -- KEK-wrapped ephemeral Data Encryption Key (envelope token, §5.2 step 3):
    -- base64(dek_nonce || wrapped_dek_ciphertext || gcm_tag).
    wrapped_dek             VARCHAR(96) NOT NULL,

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_nodes_family
        FOREIGN KEY (family_id) REFERENCES families (family_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_secure_nodes_blind_hash
    ON family_secure_nodes (blind_index_hash);
CREATE INDEX IF NOT EXISTS idx_secure_nodes_family_id
    ON family_secure_nodes (family_id);
CREATE INDEX IF NOT EXISTS idx_secure_nodes_type
    ON family_secure_nodes (family_id, node_type);

-- -----------------------------------------------------------------------------
-- Directional graph EDGES (Blueprint §4.2)
-- Relationship type is cleartext (enables DEPENDS_ON traversal); edge property
-- payloads (bus route, academic year, ...) are encrypted like node payloads.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS family_secure_edges (
    edge_id                 VARCHAR(64) PRIMARY KEY,
    family_id               VARCHAR(64) NOT NULL,
    edge_type               VARCHAR(32) NOT NULL,

    source_node_id          VARCHAR(64) NOT NULL,
    target_node_id          VARCHAR(64) NOT NULL,

    encrypted_payload_blob  TEXT,
    cryptographic_nonce     VARCHAR(24),
    key_verification_tag    VARCHAR(32),
    wrapped_dek             VARCHAR(96),

    confidence_score        NUMERIC(4, 3) NOT NULL DEFAULT 1.000
        CHECK (confidence_score >= 0 AND confidence_score <= 1),
    verified_by_user        BOOLEAN NOT NULL DEFAULT FALSE,

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_edges_family
        FOREIGN KEY (family_id) REFERENCES families (family_id) ON DELETE CASCADE,
    CONSTRAINT fk_edges_source
        FOREIGN KEY (source_node_id) REFERENCES family_secure_nodes (node_id) ON DELETE CASCADE,
    CONSTRAINT fk_edges_target
        FOREIGN KEY (target_node_id) REFERENCES family_secure_nodes (node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_secure_edges_source
    ON family_secure_edges (source_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_secure_edges_target
    ON family_secure_edges (target_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_secure_edges_family
    ON family_secure_edges (family_id);

-- -----------------------------------------------------------------------------
-- Extraction pipeline ledger (Blueprint §2 Layer 2, §3.3 routing outcomes)
-- Tracks provenance + confidence routing status for every ingested artifact.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extraction_ledger (
    extraction_id           VARCHAR(64) PRIMARY KEY,
    family_id               VARCHAR(64) NOT NULL,

    confidence_score        NUMERIC(4, 3) NOT NULL
        CHECK (confidence_score >= 0 AND confidence_score <= 1),
    confidence_band         VARCHAR(8)  NOT NULL
        CHECK (confidence_band IN ('HIGH', 'MEDIUM', 'LOW')),
    record_status           VARCHAR(24) NOT NULL
        CHECK (record_status IN ('COMMITTED', 'PENDING_VERIFICATION', 'REJECTED')),

    -- Source provenance for the Provenance Popover (§9.2).
    source_channel          VARCHAR(32),   -- gmail | msgraph | webcal | upload | voice
    source_reference        VARCHAR(256),  -- opaque message/file id
    source_document_name    VARCHAR(256),

    -- The OBLIGATION node created when a HIGH-confidence record committed.
    obligation_node_id      VARCHAR(64),

    encrypted_payload_blob  TEXT NOT NULL,
    cryptographic_nonce     VARCHAR(24) NOT NULL,
    key_verification_tag    VARCHAR(32) NOT NULL,
    wrapped_dek             VARCHAR(96) NOT NULL,

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ledger_family
        FOREIGN KEY (family_id) REFERENCES families (family_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ledger_status
    ON extraction_ledger (family_id, record_status);

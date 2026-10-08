CREATE TABLE dbo.tblentity_product
(
    -- Surrogate primary key
    EntityProductId     INT          NOT NULL IDENTITY(1,1),

    -- Relationship columns
    EntityId            INT          NOT NULL,
    ProductId           INT          NOT NULL,

    -- ── Audit columns (matching tblentity / tblproduct convention) ──
    CreateId            INT          NULL,
    CreateSessionId     INT          NULL,
    CreateTs            DATETIME     NULL,

    ModifyId            INT          NULL,
    ModifySessionId     INT          NULL,
    ModifyTs            DATETIME     NULL,

    InactiveId          INT          NULL,
    InactiveSessionId   INT          NULL,
    InactiveTs          DATETIME     NULL,

    StatusId            INT          NULL,

    ZDb                 INT          NULL,
    ZId                 INT          NULL,

    -- ── Constraints ──
    CONSTRAINT PK_tblentity_product
        PRIMARY KEY CLUSTERED (EntityProductId),

    CONSTRAINT UQ_tblentity_product_EntityId_ProductId
        UNIQUE (EntityId, ProductId),

    CONSTRAINT FK_tblentity_product_tblentity
        FOREIGN KEY (EntityId)
        REFERENCES dbo.tblentity (EntityId)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT FK_tblentity_product_tblproduct
        FOREIGN KEY (ProductId)
        REFERENCES dbo.tblproduct (ProductId)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- Support lookups from the product side
CREATE NONCLUSTERED INDEX IX_tblentity_product_ProductId
    ON dbo.tblentity_product (ProductId)
    INCLUDE (EntityId);
GO

INSERT INTO tblCost WITH ( ROWLOCK )
(
    AccountID,
    EntityID,
    CostTypeID,
    MasterCostID,
    CostCategoryID,
    AccountCost,
    InternalCost,
    CostDate,
    CurrencyID,
    CurrencyRate,
    Reversed,
    ReverseReason,
    CreateID,
    CreateSessionID,
    CreateTS,
    StatusID,
    LoadID,
    NonClientVisible,
    Deferred,
    IncursInterest
)
SELECT
    A.AccountID,
    A.EntityID,
    SC.CostTypeID,
    SC.MasterCostID,
    MC.MasterCostCategoryID,
    SC.Amount,
    0,
    A.RecoveryStartDate,
    1,
    1.0,
    NULL,
    NULL,
    1,
    {{CurrentSessionID}},
    GETDATE(),
    1,
    {{LoadID}},
    0,
    0,
    0
FROM RC_STAGING_COSTS SC WITH ( NOLOCK )
INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CONVERT(nvarchar(100), SC.Debtor_Code)
LEFT JOIN tblMasterCost MC WITH ( NOLOCK ) ON MC.MasterCostID = SC.MasterCostID
WHERE A.LoadID = {{LoadID}}
  AND SC.LoadID = {{LoadID}}
  AND SC.StatusID = 1
;

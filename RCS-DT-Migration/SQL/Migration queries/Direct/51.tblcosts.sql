WITH CTE_COSTS AS (
    SELECT   
        RC_COSTS_EXTRACT.[Debtor_Code],
        V.[CostField],
        V.[Amount]
    FROM [dbo].[RC_COSTS_EXTRACT]
    INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = RC_COSTS_EXTRACT.Debtor_Code
    CROSS APPLY (VALUES
        ('ADM', ISNULL([Chg_ADM], 0)),
        ('IBS', ISNULL([Chg_IBS], 0)),
        ('IAJ', ISNULL([Chg_IAJ], 0)),
        ('LET', ISNULL([Chg_LET], 0)),
        ('POR', ISNULL([Chg_POR], 0)),
        ('MPL', ISNULL([Chg_MPL], 0)),
        ('BNK', ISNULL([Chg_BNK], 0)),
        ('SHR', ISNULL([Chg_SHR], 0)),
        ('SHN', ISNULL([Chg_SHN], 0)),
        ('LOC', ISNULL([Chg_LOC], 0)),
        ('FCA', ISNULL([Chg_FCA], 0)),
        ('REP', ISNULL([Chg_REP], 0)),
        ('SEC', ISNULL([Chg_SEC], 0)),
        ('COU', ISNULL([Chg_COU], 0)),
        ('PRE', ISNULL([Chg_PRE], 0)),
        ('SSC', ISNULL([Chg_SSC], 0)),
        ('ESC', ISNULL([Chg_ESC], 0)),
        ('BAR', ISNULL([Chg_BAR], 0)),
        ('CRT', ISNULL([Chg_CRT], 0)),
        ('SRV', ISNULL([Chg_SRV], 0)),
        ('ATS', ISNULL([Chg_ATS], 0)),
        ('ADS', ISNULL([Chg_ADS], 0)),
        ('KIL', ISNULL([Chg_KIL], 0)),
        ('CMO', ISNULL([Chg_CMO], 0)),
        ('HEA', ISNULL([Chg_HEA], 0)),
        ('AFF', ISNULL([Chg_AFF], 0)),
        ('OTH', ISNULL([Chg_OTH], 0)),
        ('COJ', ISNULL([Chg_COJ], 0)),
        ('ADR', ISNULL([Chg_ADR], 0)),
        ('ADN', ISNULL([Chg_ADN], 0)),
        ('BAI', ISNULL([Chg_BAI], 0)),
        ('REG', ISNULL([Chg_REG], 0)),
        ('DEBR', ISNULL([Chg_DEBR], 0)),
        ('DEBW', ISNULL([Chg_DEBW], 0)),
        ('SERV', ISNULL([Chg_SERV], 0)),
        ('SUND', ISNULL([Chg_SUND], 0)),
        ('UIL', ISNULL([Chg_UIL], 0)),
        ('SCN', ISNULL([Chg_SCN], 0)),
        ('VLC', ISNULL([Chg_VLC], 0)),
        ('ILD', ISNULL([Chg_ILD], 0)),
        ('VLD', ISNULL([Chg_VLD], 0)),
        ('ILC', ISNULL([Chg_ILC], 0)),
        ('PHC', ISNULL([Chg_PHC], 0)),
        ('AHF', ISNULL([Chg_AHF], 0)),
        ('ICS', ISNULL([Chg_ICS], 0)),
        ('LIST', ISNULL([Chg_LIST], 0)),
        ('SHRF', ISNULL([Chg_SHRF], 0)),
        ('SHRC', ISNULL([Chg_SHRC], 0)),
        ('SRVI', ISNULL([Chg_SRVI], 0)),
        ('SRVC', ISNULL([Chg_SRVC], 0)),
        ('CLC', ISNULL([Chg_CLC], 0)),
        ('STB', ISNULL([Chg_STB], 0)),
        ('SEB', ISNULL([Chg_SEB], 0)),
        ('AUD', ISNULL([Chg_AUD], 0)),
        ('SCOS', ISNULL([Chg_SCOS], 0)),
        ('ARC', ISNULL([Chg_ARC], 0)),
        ('ICL', ISNULL([Chg_ICL], 0)),
        ('SAP', ISNULL([Chg_SAP], 0)),
        ('COL', ISNULL([Chg_COL], 0))
    ) V([CostField], [Amount])
    WHERE A.LoadID = {{LoadID}}
    AND V.[Amount] <> 0
)

INSERT INTO tblCost WITH ( ROWLOCK )
(
    AccountID,
    CostTypeID,
    MasterCostID,
    AccountCost,
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
    CTM.CostTypeIDDestination,
    CASE
        WHEN CTE_COSTS.CostField = 'COL' THEN 12 
        ELSE 2
    END,
    CTE_COSTS.Amount,
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
FROM CTE_COSTS
INNER JOIN CSRC_CostTypeMapping CTM ON CTM.CostTypeCode = CTE_COSTS.CostField
INNER JOIN tblAccount A ON A.AccountNumberPrevious = CTE_COSTS.Debtor_Code
WHERE A.LoadID = {{LoadID}}
;
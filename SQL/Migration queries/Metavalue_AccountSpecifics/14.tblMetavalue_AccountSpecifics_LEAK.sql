WITH 
Metafield_accountspecifics_details AS (

	SELECT  
	MetaField_AccountSpecifics AS Name,
	MetaField_AccountSpecificsID AS MFID

	FROM    tblMetaField_AccountSpecifics
	WHERE   MetaField_AccountSpecificsGroupID = {{AccountSpecificsGroupID_LEAK}}
),
 
CTE_LEAKData AS(
    SELECT 
    RCDR.Full_Debt_Code, 
    V.[Name],
    V.[ValueString],
    V.[ValueInteger],
    V.[ValueDecimal],
    V.[ValueDatetime]
    FROM RC_DRDEBTINFO RCDR
    CROSS APPLY (VALUES
        ('Contact_Details', Contact_Details,NULL,NULL,NULL),
        ('Leak_Fixed',Leak_Fixed, NULL,NULL,NULL),
        ('Leak_Issue',Leak_Issue, NULL,NULL,NULL),
        ('Leak_Meter_Reading',Leak_Meter_Reading, NULL,NULL,NULL)
    ) V([Name], [ValueString], [ValueInteger], [ValueDecimal], [ValueDatetime])
    --WHERE V.ValueDatetime is NOT NULL or V.ValueDecimal is NOT NULL 
    --or V.ValueInteger is NOT NULL or V.ValueString is NOT NULL
)
--Check Which Columns are not mapped in debtrak 
-- SELECT DISTINCT
-- Name,
-- MetaField_AccountSpecifics,
-- MetaField_AccountSpecificsID,
-- MetaField_AccountSpecificsGroupID
-- FROM CTE_LEAKData
-- LEFT JOIN tblMetaField_AccountSpecifics on MetaField_AccountSpecifics = Name
-- --WHERE MetaField_AccountSpecifics IS NOT NULL

INSERT  INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
       ( MetaField_AccountSpecificsID ,
         MetaValue_AccountSpecificsGroupID ,
         ValueString ,
         ValueInt ,
         ValueDecimal ,
         ValueDateTime ,
         CreateID ,
         CreateSessionID ,
         CreateTS ,
         StatusID
       )

    SELECT  
    MF.MetaField_AccountSpecificsID ,
    MVG.MetaValue_AccountSpecificsGroupID ,
    CTE_LEAKData.ValueString ,
    CTE_LEAKData.ValueInteger ,
    CTE_LEAKData.ValueDecimal ,
    CTE_LEAKData.ValueDateTime ,
    1 ,
    {{CurrentSessionID}} ,
    GETDATE() ,
    1
    FROM    CTE_LEAKData
            INNER JOIN Metafield_accountspecifics_details Meta on Meta.Name = CTE_LEAKData.Name
            INNER JOIN tblAccount A ON A.AccountNumberPrevious = CTE_LEAKData.Full_Debt_Code
            INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = Meta.MFID
            INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                    AND MVG.Z_AccountID = A.AccountID
            WHERE   A.LoadID = {{LoadID}}
            AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)
            ;
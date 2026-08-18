WITH 
Metafield_accountspecifics_details AS (

	SELECT  
	MetaField_AccountSpecifics AS Name,
	MetaField_AccountSpecificsID AS MFID

	FROM    tblMetaField_AccountSpecifics
	WHERE   MetaField_AccountSpecificsGroupID = 1832--{{AccountSpecificsGroupID_INOU}}
),
 
CTE_INOUData AS(
    SELECT 
    RCDR.Full_Debt_Code, 
    V.[Name],
    V.[ValueString],
    V.[ValueInteger],
    V.[ValueDecimal],
    V.[ValueDatetime]
    FROM RC_DRDEBTINFO RCDR
    CROSS APPLY (VALUES
        ('Settled_Date', NULL,NULL,NULL,Settled_Date),
        ('Solicitor_Name',Solicitor_Name, NULL,NULL,NULL),
        ('Solicitor_Address_1',Solicitor_Address_1, NULL,NULL,NULL),
        ('Solicitor_Address_2',Solicitor_Address_2, NULL,NULL,NULL),
        ('Solicitor_Address_3',Solicitor_Address_3, NULL,NULL,NULL),
        ('Solicitor_Address_Sub',Solicitor_Address_Sub, NULL,NULL,NULL),
        ('Solicitor_Address_State',Solicitor_Address_State, NULL,NULL,NULL),
        ('Solicitor_Address_Pcode',Solicitor_Address_Pcode, NULL,NULL,NULL),
        ('Solicitor_Contact',Solicitor_Contact, NULL,NULL,NULL)
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
-- FROM CTE_INOUData
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
    CTE_INOUData.ValueString ,
    CTE_INOUData.ValueInteger ,
    CTE_INOUData.ValueDecimal ,
    CTE_INOUData.ValueDateTime ,
    1 ,
    {{CurrentSessionID}} ,
    GETDATE() ,
    1
    FROM    CTE_INOUData
            INNER JOIN Metafield_accountspecifics_details Meta on Meta.Name = CTE_INOUData.Name
            INNER JOIN tblAccount A ON A.AccountNumberPrevious = CTE_INOUData.Full_Debt_Code
            INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = Meta.MFID
            INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                    AND MVG.Z_AccountID = A.AccountID
            WHERE   A.LoadID = {{LoadID}}
            AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)
            ;
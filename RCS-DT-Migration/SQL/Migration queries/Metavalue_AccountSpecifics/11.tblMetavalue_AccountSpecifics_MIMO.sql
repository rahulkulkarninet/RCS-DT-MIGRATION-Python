WITH 
Metafield_accountspecifics_details AS (

	SELECT  
	MetaField_AccountSpecifics AS Name,
	MetaField_AccountSpecificsID AS MFID

	FROM    tblMetaField_AccountSpecifics
	WHERE   MetaField_AccountSpecificsGroupID = {{AccountSpecificsGroupID_MIMO}}
),
 
CTE_MIMOData AS(
    SELECT 
    RCDR.Full_Debt_Code, 
    V.[Name],
    V.[ValueString],
    V.[ValueInteger],
    V.[ValueDecimal],
    V.[ValueDatetime]
    FROM RC_DRDEBTINFO RCDR
    CROSS APPLY (VALUES
        ('Move_in_Date_Supply_Start_Date', NULL,NULL,NULL,Move_in_Date),
        ('Move_out_Date_Supply_End_Date', NULL,NULL,NULL,Move_out_Date),
        ('Agent_Name',Agent_Name, NULL,NULL,NULL),
        ('Agent_Address_1',Agent_Address_1, NULL,NULL,NULL),
        ('Agent_Address_2',Agent_Address_2, NULL,NULL,NULL),
        ('Agent_Suburb',Agent_Suburb, NULL,NULL,NULL),
        ('Agent_State',Agent_State, NULL,NULL,NULL),
        ('Agent_Postcode',Agent_Postcode,NULL,NULL,NULL),
        ('Agent_Phone_No',Agent_Phone_No,NULL,NULL,NULL),
        ('New_Postal_Addr1',New_Postal_Addr1,NULL,NULL,NULL),
        ('New_Postal_Addr2',New_Postal_Addr2,NULL,NULL,NULL),
        ('New_Postal_Addr3',New_Postal_Addr3,NULL,NULL,NULL),
        ('New_Postal_Sub',New_Postal_Sub,NULL,NULL,NULL),
        ('New_Postal_State',New_Postal_State,NULL,NULL,NULL),
        ('New_Postal_Pcode',New_Postal_Pcode, NULL,NULL,NULL)
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
-- FROM CTE_MIMOData
-- LEFT JOIN tblMetaField_AccountSpecifics on MetaField_AccountSpecifics = Name
-- WHERE MetaField_AccountSpecifics IS NOT NULL

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
    CTE_MIMOData.ValueString ,
    CTE_MIMOData.ValueInteger ,
    CTE_MIMOData.ValueDecimal ,
    CTE_MIMOData.ValueDateTime ,
    1 ,
    {{CurrentSessionID}} ,
    GETDATE() ,
    1
    FROM    CTE_MIMOData
            INNER JOIN Metafield_accountspecifics_details Meta on Meta.Name = CTE_MIMOData.Name
            INNER JOIN tblAccount A ON A.AccountNumberPrevious = CTE_MIMOData.Full_Debt_Code
            INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = Meta.MFID
            INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                    AND MVG.Z_AccountID = A.AccountID
            WHERE   A.LoadID = {{LoadID}}
            AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)
            ;
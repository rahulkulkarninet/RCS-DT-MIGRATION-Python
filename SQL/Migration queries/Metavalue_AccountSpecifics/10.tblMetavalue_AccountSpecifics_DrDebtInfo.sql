WITH 
Metafield_accountspecifics_details AS (

	SELECT  
	MetaField_AccountSpecifics AS Name,
	MetaField_AccountSpecificsID AS MFID

	FROM    tblMetaField_AccountSpecifics
	WHERE   MetaField_AccountSpecificsGroupID = {{AccountSpecificsGroupID_DrDebtInfo}}
),
 
CTE_DrDbInfoData AS(
    SELECT 
    RCDR.Full_Debt_Code, 
    V.[Name],
    V.[ValueString],
    V.[ValueInteger],
    V.[ValueDecimal],
    V.[ValueDatetime]
    FROM RC_DRDEBTINFO RCDR
    CROSS APPLY (VALUES
        ('Property_Address_Line_1',Property_Address_Line_1, NULL,NULL,NULL),
        ('Property_Address_Line_2',Property_Address_Line_2, NULL,NULL,NULL),
        ('Property_Address_Line_3',Property_Address_Line_3, NULL,NULL,NULL),
        ('Property_Suburb',Property_Suburb, NULL,NULL,NULL),
        ('Property_State',Property_State, NULL,NULL,NULL),
        ('Property_Post_Code',Property_Post_Code, NULL,NULL,NULL),
        ('Account_Type_Additional_Worktype',Account_Type_Additional_Worktype, NULL,NULL,NULL),
        ('Overdue_Amount',NULL,NULL,Overdue_Amount,NULL),
        ('Cycle_Days',NULL,NULL,Cycle_Days,NULL),
        ('Over_Limit',NULL,NULL,Over_Limit,NULL),
        ('Credit_Limit',NULL,NULL,Credit_Limit,NULL),
        ('Credit_Listing',NULL,NULL,NULL,Credit_Listing),
        ('S88_Date_DN_Expiry_Date',NULL,NULL,NULL,S88_Date_DN_Expiry_Date),
        ('3rd_Party_Auth',NULL,[_3rd_Party_Auth],NULL,NULL),
        ('BPAY_reference',BPAY_reference, NULL,NULL,NULL),
        ('Last_Monetary_Amount_Last_Pay_Amount',NULL,NULL,Last_Monetary_Amount_Last_Pay_Amount,NULL),
        ('Last_Monetary_Type_Last_Payment_Type',Last_Monetary_Type_Last_Payment_Type, NULL,NULL,NULL),
        ('Last_Monetary_Date_Last_Pay_Date',NULL,NULL,NULL,Last_Monetary_Date_Last_Pay_Date),
        ('Concession_Concession_Type',Concession_Concession_Type, NULL,NULL,NULL),
        ('Arrears_Past_Due_Upd',Arrears_Past_Due_Upd,NULL,NULL,NULL),
        ('Risk_Client_Risk_Code',Risk_Client_Risk_Code, NULL,NULL,NULL),
        ('Property_Reference_Di_Proptype',Property_Reference_Di_Proptype, NULL,NULL,NULL),
        ('Barcode_Data_Unique_Key',Barcode_Data_Unique_Key, NULL,NULL,NULL),
        ('Ocr_Line',Ocr_Line, NULL,NULL,NULL),
        ('Dhs_Tenant',Dhs_Tenant, NULL,NULL,NULL),
        ('Account_Authorisation',Account_Authorisation, NULL,NULL,NULL),
        ('Payplan_Status_Receipt_Details',Payplan_Status_Receipt_Details, NULL,NULL,NULL),
        ('Expected_Payment_Date',NULL,NULL,NULL,Expected_Payment_Date),
        ('Score_Colour_On_Load',Score_Colour_On_Load, NULL,NULL,NULL),
        ('Solicitor_Contact',Solicitor_Contact, NULL,NULL,NULL),
        ('Tdx_Closure_Reason_Code',Tdx_Closure_Reason_Code, NULL,NULL,NULL),
        ('Date_Account_Opened', NULL,NULL,NULL,Date_Account_Opened),
        ('Total_Paid', NULL,NULL,Total_Paid,NULL),
        ('Amount_Deposited', NULL,NULL,Amount_Deposited,NULL),
        ('Original_Debt_Amount', NULL,NULL,Original_Debt_Amount,NULL),
        ('Amount_Outstanding', NULL,NULL,Amount_Outstanding,NULL),
        ('Fee_Amount', NULL,NULL,Fee_Amount,NULL),
        ('Amount_Outstanding_Update', NULL,NULL,Amount_Outstanding_Update,NULL),
        ('Contact_Details', Contact_Details,NULL,NULL,NULL),
        ('Id_Type', Id_Type,NULL,NULL,NULL),
        ('Id_Number', Id_Number,NULL,NULL,NULL),
        ('Client_Advice', Client_Advice,NULL,NULL,NULL),
        ('Account_Status', Account_Status,NULL,NULL,NULL),
        ('Due_Date', NULL,NULL,NULL,Due_Date),
        ('Last_Invoice_Date', NULL,NULL,NULL,Last_Invoice_Date),
        ('End_Date', NULL,NULL,NULL,End_Date),
        ('_6Q_Date', NULL,NULL,NULL,_6Q_Date),
        ('_21D_Date', NULL,NULL,NULL,_21D_Date),
        ('Date_Payment_Made',NULL,NULL,NULL,Date_Payment_Made) 
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
-- FROM CTE_DrDbInfoData
-- LEFT JOIN tblMetaField_AccountSpecifics on MetaField_AccountSpecifics = Name
-- WHERE MetaField_AccountSpecifics IS NULL

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
    CTE_DrDbInfoData.ValueString ,
    CTE_DrDbInfoData.ValueInteger ,
    CTE_DrDbInfoData.ValueDecimal ,
    CTE_DrDbInfoData.ValueDateTime ,
    1 ,
    {{CurrentSessionID}} ,
    GETDATE() ,
    1
    FROM    CTE_DrDbInfoData
            INNER JOIN Metafield_accountspecifics_details Meta on Meta.Name = CTE_DrDbInfoData.Name
            INNER JOIN tblAccount A ON A.AccountNumberPrevious = CTE_DrDbInfoData.Full_Debt_Code
            INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = Meta.MFID
            INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                    AND MVG.Z_AccountID = A.AccountID
            WHERE   A.LoadID = {{LoadID}}
            AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)
            ;
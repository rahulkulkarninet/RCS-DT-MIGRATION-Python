WITH 
Metafield_accountspecifics_details AS (

	SELECT  
	MetaField_AccountSpecifics AS Name,
	MetaField_AccountSpecificsID AS MFID

	FROM    tblMetaField_AccountSpecifics
	WHERE   MetaField_AccountSpecificsGroupID = {{AccountSpecificsGroupID_DebtReferenceNumbers}}
),
RC_Unpivot AS (
	SELECT
	RCA.Full_Debt_Code,
	V.[Name],
	V.[Value]
	FROM RC_ACCOUNT_EXTRACT RCA
	CROSS APPLY (VALUES
		('DebtRefNo',RCA.Debt_Ref_No),
		('DebtRefNo2',RCA.Debt_Ref_No2),
		('DebtRefNo3',RCA.Debt_Ref_No3),
		('DebtRefNo4',RCA.Debt_Ref_No_4)
	) V([Name],[Value])
	WHERE V.Value is not null
)

INSERT  INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
	(	MetaField_AccountSpecificsID ,
		MetaValue_AccountSpecificsGroupID ,
		ValueString ,
		CreateID ,
		CreateSessionID ,
		CreateTS ,
		StatusID
	)

	SELECT 
		MF.MetaField_AccountSpecificsID ,
		MVG.MetaValue_AccountSpecificsGroupID ,
		ISNULL(RC.Value, '') ,
		1 ,
		{{CurrentSessionID}} ,
		GETDATE() ,
		1

		from RC_Unpivot RC
		INNER JOIN Metafield_accountspecifics_details Meta on Meta.Name = RC.Name
		INNER JOIN tblAccount A ON A.AccountNumberPrevious = RC.Full_Debt_Code
		INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = Meta.MFID
		INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
																AND MVG.Z_AccountID = A.AccountID
		WHERE   A.LoadID = {{LoadID}}
				AND (Value IS NOT NULL)
				;

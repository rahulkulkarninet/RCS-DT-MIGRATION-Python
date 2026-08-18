INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,  
		  FirstName,
          LastName ,
          DOB ,          
          IsTemporaryPassword ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2 ,
          Z_REF3
        )
		-- Insured Party
        SELECT DISTINCT
                {{LoadID}} ,
                0 , --IsUser
                1 ,	--IsPerson
			    {{ContactTypeID_Insured}},	--ContactTypeID 
				Insureds_First_Name,
                Insureds_Company_Surname ,
                NULL ,                
                1 ,                                
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                Full_Debt_Code ,
                CAST(Short_Debt_Code AS NVARCHAR) + '*INS' ,
                NULL
        FROM    RC_ACCOUNT_EXTRACT 
		WHERE   Insureds_Company_Surname IS NOT NULL
 
UNION ALL
        -- Insured Driver
        SELECT
                {{LoadID}} ,
                0 , --IsUser
                1 ,	--IsPerson
			    {{ContactTypeID_InsuredDriver}},	--ContactTypeID 
				NULL,
                I.InsuredDriverName ,
                NULL ,                
                1 ,                                
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*IPD' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.InsuredDriverName IS NOT NULL

UNION ALL
        -- Third Party Driver
        SELECT
                {{LoadID}} ,
                0 , --IsUser
                1 ,	--IsPerson
			    {{ContactTypeID_ThirdPartyDriver}},	--ContactTypeID 
				NULL,
                I.TPD_Name ,
                NULL ,                
                1 ,                                
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*TPD' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.TPD_Name IS NOT NULL

UNION ALL

        -- Third Party Owner
        SELECT
                {{LoadID}} ,
                0 , --IsUser
                1 ,	--IsPerson
			    {{ContactTypeID_ThirdPartyOwner}},	--ContactTypeID 
				I.TPO_Firstname,
                I.TPO_Surname ,
                NULL ,                
                1 ,                                
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*TPO' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.TPO_Surname IS NOT NULL

UNION ALL
		-- Third Party Insurer
        SELECT
                {{LoadID}} ,
                0 , --IsUser
                1 ,	--IsPerson
			    {{ContactTypeID_ThirdPartyInsurer}},	--ContactTypeID 
				NULL,
                ISNULL(I.InsurerNameonDocument,I.InsurerCode) ,
                NULL ,                
                1 ,                                
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*TPI' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.InsurerCode IS NOT NULL or I.InsurerNameOnDocument IS NOT NULL


INSERT  INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
		-- Insured party
        SELECT
	DISTINCT    C.ContactID ,
                {{ContactDetailTypeID_Email}} ,
                RCA.Plaintiff_Email_Address ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    RC_ACCOUNT_EXTRACT RCA
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(RCA.Short_Debt_Code as nvarchar(10)) + '*INS'
        WHERE   LEN(RCA.Plaintiff_Email_Address) > 0 AND C.LoadID = {{LoadID}}

UNION ALL
        -- Insured rep
        SELECT
	DISTINCT    C.ContactID ,
                {{ContactDetailTypeID_Email}} ,
                I.RepEmail ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*IPR'
        WHERE   (LEN(I.RepEmail) > 0 and I.RepContactFirstYN = 'Y') AND C.LoadID = {{LoadID}}


UNION ALL

        -- Insured Driver
        SELECT
	DISTINCT    C.ContactID ,
                {{ContactDetailTypeID_Email}} ,
                I.InsuredDriverEmail ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*IPD'
        WHERE   LEN(I.InsuredDriverEmail) > 0 AND C.LoadID = {{LoadID}}


UNION ALL

        -- Third Party Driver
        SELECT
	DISTINCT    C.ContactID ,
                {{ContactDetailTypeID_Email}} ,
                I.TPD_Email ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*TPD'
        WHERE   LEN(I.TPD_Email) > 0 AND C.LoadID = {{LoadID}}


UNION ALL

        -- Third Party Owner
        SELECT
	DISTINCT    C.ContactID ,
                {{ContactDetailTypeID_Email}} ,
                I.TPO_Email ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*TPO'
        WHERE   LEN(I.TPO_Email) > 0 AND C.LoadID = {{LoadID}}

UNION ALL

        -- Third Party Insurer
        SELECT
	DISTINCT    C.ContactID ,
                {{ContactDetailTypeID_Email}} ,
                I.InsurerEmail ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*TPI'
        WHERE   LEN(I.InsurerEmail) > 0 AND C.LoadID = {{LoadID}}
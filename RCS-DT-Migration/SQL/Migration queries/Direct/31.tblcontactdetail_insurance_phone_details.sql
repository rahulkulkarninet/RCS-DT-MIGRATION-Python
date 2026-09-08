INSERT INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
		-- Insured party (mobile)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Mobile}} ,
            RCA.Plaint_Ph_M ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_ACCOUNT_EXTRACT RCA
            INNER JOIN tblContact C WITH ( NOLOCK ) ON RCA.Full_Debt_Code = C.Z_REF
        WHERE
            LEN(RCA.Plaint_Ph_M) > 0 and C.LoadID = {{LoadID}}
			AND RCA.Insureds_Company_Surname IS NOT NULL AND C.Z_REF2 = CAST(RCA.Short_Debt_Code AS nvarchar) + '*INS'

UNION ALL
        -- Insured party (home ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Home}} ,
            RCA.Plaint_Phone_H ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_ACCOUNT_EXTRACT RCA
            INNER JOIN tblContact C WITH ( NOLOCK ) ON RCA.Full_Debt_Code = C.Z_REF
        WHERE
            LEN(RCA.Plaint_Phone_H) > 0 and C.LoadID = {{LoadID}}
			AND RCA.Insureds_Company_Surname IS NOT NULL AND C.Z_REF2 = CAST(RCA.Short_Debt_Code AS nvarchar) + '*INS'

UNION ALL

        -- Insured party (work ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Work}} ,
            RCA.Pl_Phone_W ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_ACCOUNT_EXTRACT RCA
            INNER JOIN tblContact C WITH ( NOLOCK ) ON RCA.Full_Debt_Code = C.Z_REF
        WHERE
            LEN(RCA.Pl_Phone_W) > 0 and C.LoadID = {{LoadID}}
			AND RCA.Insureds_Company_Surname IS NOT NULL AND C.Z_REF2 = CAST(RCA.Short_Debt_Code AS nvarchar) + '*INS'

UNION ALL
        -- Insured Representative (all phone nos)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Mobile}} ,
            X.Value ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
            CROSS APPLY dbo.fnPipeDelimitedStringIntoTable(I.RepPhoneNo) X
        WHERE
            LEN(I.RepPhoneNo) > 0 and C.LoadID = {{LoadID}}
			AND I.RepName IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*IPR'

UNION ALL
        -- Insured Driver (Home ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Home}} ,
            I.InsuredDriverHomePhome ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.InsuredDriverHomePhome) > 0 and C.LoadID = {{LoadID}}
			AND I.InsuredDriverName IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*IPD'

UNION ALL

        -- Insured Driver (work ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Work}} ,
            I.InsuredDriverWorkPhone ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.InsuredDriverWorkPhone) > 0 and C.LoadID = {{LoadID}}
			AND I.InsuredDriverName IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*IPD'

UNION ALL
        -- Third Party Driver (Home ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Home}} ,
            I.TPD_HomePhone ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPD_HomePhone) > 0 and C.LoadID = {{LoadID}}
			AND I.TPD_Name IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPD'

UNION ALL

        -- Third Party Driver (work ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Work}} ,
            I.TPD_WorkPhone ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPD_WorkPhone) > 0 and C.LoadID = {{LoadID}}
			AND I.TPD_Name IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPD'

UNION ALL

        -- Third Party Driver (mobile)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Work}} ,
            I.TPD_Mobile ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPD_Mobile) > 0 and C.LoadID = {{LoadID}}
			AND I.TPD_Name IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPD'


UNION ALL
        -- Third Party Owner (Home ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Home}} ,
            I.TPO_HomePhone ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPO_HomePhone) > 0 and C.LoadID = {{LoadID}}
			AND I.TPO_Surname IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPO'

UNION ALL

        -- Third Party Owner (work ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Work}} ,
            I.TPO_WorkPhone ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPO_WorkPhone) > 0 and C.LoadID = {{LoadID}}
			AND I.TPO_Surname IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPO'

UNION ALL
        -- Third Party Insurer (Home ph)
        SELECT
            C.ContactID ,
            {{ContactDetailTypeID_Home}} ,
            I.InsurerPhoneNo ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.InsurerPhoneNo) > 0 and C.LoadID = {{LoadID}}
			AND (I.InsurerNameOnDocument IS NOT NULL OR I.InsurerCode IS NOT NULL) AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPI'

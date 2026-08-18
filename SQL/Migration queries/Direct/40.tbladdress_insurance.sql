INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
		-- Insured party
        SELECT DISTINCT 
		        C.ContactID ,
                {{AddressTypeID_Mail}} ,
                1 ,
                ISNULL(RCA.Address_Line1, '') + CHAR(13) + CHAR(10) + ISNULL(RCA.Address_Line2, ''),
                RCA.Pl_State ,
                RCA.Plaint_Suburb ,
                Pl_PCode ,
                {{DefaultCountryID}} ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_ACCOUNT_EXTRACT RCA ON CAST(RCA.Short_Debt_Code AS VARCHAR) + '*INS' = C.Z_REF2
        WHERE   LEN(RCA.Address_Line1) > 0 AND C.LoadID = {{LoadID}}

UNION ALL
        -- Insured representative
        SELECT DISTINCT 
		        C.ContactID ,
                {{AddressTypeID_Mail}} ,
                1 ,
                ISNULL(I.REPAddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.RepAddressLine2, ''),
                I.RepState ,
                I.RepSuburb ,
                I.RepPcode ,
                {{DefaultCountryID}} ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*IPR' = C.Z_REF2
        WHERE   (LEN(I.RepAddressLine1) > 0 AND I.RepContactFirstYN = 'Y' )AND C.LoadID = {{LoadID}}

UNION ALL
        -- Insured driver
        SELECT DISTINCT 
		        C.ContactID ,
                {{AddressTypeID_Mail}} ,
                1 ,
                ISNULL(I.InsuredDriverAddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.InsuredDriverAddressLine2, ''),
                I.InsuredDriverState ,
                I.InsuredDriverSuburb ,
                I.InsuredDriverPCode ,
                {{DefaultCountryID}} ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*IPD' = C.Z_REF2
        WHERE   LEN(I.InsuredDriverAddressLine1) > 0 AND C.LoadID = {{LoadID}}


UNION ALL
        -- Third party driver
        SELECT DISTINCT 
		        C.ContactID ,
                {{AddressTypeID_Mail}} ,
                1 ,
                ISNULL(I.TPD_AddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.TPD_AddressLine2, ''),
                I.TPD_State ,
                I.TPD_Suburb ,
                I.TPD_PCode ,
                {{DefaultCountryID}} ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*TPD' = C.Z_REF2
        WHERE   LEN(I.TPD_AddressLine1) > 0 AND C.LoadID = {{LoadID}}


UNION ALL
        -- Third Party owner
        SELECT DISTINCT 
		        C.ContactID ,
                {{AddressTypeID_Mail}} ,
                1 ,
                ISNULL(I.TPO_AddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.TPO_AddressLine2, ''),
                I.TPO_State ,
                I.TPO_Suburb ,
                I.TPO_PCode ,
                {{DefaultCountryID}} ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                C.CreateTS ,
                {{LoadID}}
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*TPO' = C.Z_REF2
        WHERE   LEN(I.TPO_AddressLine1) > 0 AND C.LoadID = {{LoadID}}


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
        SELECT DISTINCT
            C.ContactID,
            {{ContactDetailTypeID_Email}},
            LTRIM(RTRIM(X.value)) AS Value,
            1,
            1,
            {{CurrentSessionID}},
            C.CreateTS,
            {{LoadID}}
        FROM RC_DEBTOR RCC
        INNER JOIN tblContact C WITH (NOLOCK) ON C.Z_REF2 = RCC.Debtor_Code
        CROSS APPLY STRING_SPLIT(RCC.Email_Addr, '|') X
        WHERE LEN(RCC.Email_Addr) > 0
                AND C.LoadID = {{LoadID}}
                AND LTRIM(RTRIM(X.value)) != ''  -- Filter out empty values
;

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



    SELECT
        C.ContactID,
        {{ContactDetailTypeID_Mobile}},
        LTRIM(RTRIM(X.value)) AS Value,
        1,
        1,
        {{CurrentSessionID}},
        GETDATE(),
        {{LoadID}}
    FROM RC_RELATEDPARTY RPA
    INNER JOIN tblContact C WITH (NOLOCK) ON RPA.ZID = C.Z_REF2
    CROSS APPLY STRING_SPLIT(RPA.Phone_No, '|') X
    WHERE LEN(RPA.Phone_No) > 0 
            AND C.LoadID = {{LoadID}}
            AND LTRIM(RTRIM(X.value)) != ''  -- Filter out empty values
;
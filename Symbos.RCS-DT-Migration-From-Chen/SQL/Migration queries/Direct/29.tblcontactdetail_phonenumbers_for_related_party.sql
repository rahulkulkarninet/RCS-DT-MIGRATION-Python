
INSERT INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          IsPrimary ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
    SELECT  C.ContactID ,
            DT.ContactDetailTypeID ,
            LTRIM(RTRIM(P.value)) AS Value ,
            MAX(CASE WHEN LTRIM(RTRIM(ISNULL(F.value, ''))) = '1'
                     THEN 1 ELSE 0 END) ,
            1 ,
            1 ,
            {{CurrentSessionID}} ,
            GETDATE() ,
            {{LoadID}}
    FROM    RC_RELATEDPARTY RPA
            INNER JOIN tblContact C WITH ( NOLOCK )
                    ON RPA.ZID = C.Z_REF2
                       AND C.LoadID = {{LoadID}}
            CROSS APPLY STRING_SPLIT(RPA.Phone_No, '|', 1) P
            OUTER APPLY ( SELECT S.value
                          FROM   STRING_SPLIT(RPA.Phone_Type, '|', 1) S
                          WHERE  S.ordinal = P.ordinal ) T
            OUTER APPLY ( SELECT S.value
                          FROM   STRING_SPLIT(RPA.Phone_Preferred_Flag, '|', 1) S
                          WHERE  S.ordinal = P.ordinal ) F
            CROSS APPLY ( VALUES ( CASE UPPER(LTRIM(RTRIM(ISNULL(T.value, ''))))
                                     WHEN 'M' THEN {{ContactDetailTypeID_Mobile}}
                                     WHEN 'W' THEN {{ContactDetailTypeID_Work}}
                                     WHEN 'H' THEN {{ContactDetailTypeID_Home}}
                                     ELSE {{ContactDetailTypeID_Mobile}}
                                   END ) ) AS DT ( ContactDetailTypeID )
    WHERE   LEN(ISNULL(RPA.Phone_No, '')) > 0
            AND LTRIM(RTRIM(P.value)) != ''  -- Filter out empty values
    GROUP BY C.ContactID ,
            DT.ContactDetailTypeID ,
            LTRIM(RTRIM(P.value))
;

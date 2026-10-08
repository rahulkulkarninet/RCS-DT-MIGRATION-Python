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
        SELECT
	DISTINCT    C.ContactID ,
                {{ContactDetailTypeID_Email}},
                RPA.Email_Address ,
                1 ,
                1 ,
                {{CurrentSessionID}},
                C.CreateTS ,
                {{LoadID}}
        FROM    RC_RELATEDPARTY RPA
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = RPA.ZID
        WHERE   LEN(RPA.Email_Address) > 0 AND C.LoadID = {{LoadID}}
;

INSERT  INTO tblContactDetailAudit WITH ( ROWLOCK )
        ( ContactDetailID ,
          AuditTS ,
          ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    CD.ContactDetailID ,
                GETDATE() ,
                CD.ContactID ,
                CD.ContactDetailTypeID ,
                CD.ContactDetail ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                CD.CreateTS ,
                {{LoadID}}
        FROM    tblContactDetail CD
        WHERE   CD.LoadID = {{LoadID}}
                AND CD.StatusID = 1
;
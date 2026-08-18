INSERT  INTO tblCommunication_Contact
        ( CommunicationID ,
          ContactID ,
          CommunicationMethodID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  Comm.CommunicationID ,
                C.ContactID ,
                1 ,  --LETTER
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                {{LoadID}}
        FROM    RC_DOCHIST_EXTRACT D WITH ( NOLOCK )
                INNER JOIN tblCommunication Comm WITH ( NOLOCK ) ON ( Comm.Z_REF = D.Note_Key
                                                                      AND Comm.LoadID = {{LoadID}}
                                                                    )
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON Comm.Z_REF2 = A.AccountNumberPrevious
                INNER JOIN tblContact C with ( NOLOCK ) ON C.Z_REF2 = D.Multi_Letter_Keys
        WHERE   A.LoadID = {{LoadID}}
                AND Comm.LoadID = {{LoadID}}
                AND A.StatusID = 1
                AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')
;
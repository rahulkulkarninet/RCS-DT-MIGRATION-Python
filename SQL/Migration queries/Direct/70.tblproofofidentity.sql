INSERT  INTO tblProofOfIdentity
        ( AccountID ,
          ProofOfIdentityTS ,
          Type ,
          POICompleted ,
          NoAnswerBusy ,
          LeftMessage ,
          WrongNumber ,
          DisconnectedNumber ,
          LeftNumberOnVoicemail ,
          NoMessageLeft ,
          CustomerTerminatedCall ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  A.AccountID ,
                POI.POI_Date ,
                POI.Type ,
                POI.POI_Completed ,
                POI.No_Answer_Busy ,
                POI.Left_Message ,
                POI.Wrong_Number ,
                POI.Disconnected_Number ,
                POI.Left_Number_On_Voicemail ,
                POI.No_Message_Left ,
                POI.Customer_Terminated_Call ,
                1 ,
                {{CurrentSessionID}} ,
                POI.POI_Date , --GETDATE(),
                1 ,
                {{LoadID}}
        FROM    RC_POI POI WITH ( NOLOCK )
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = POI.Extended_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
;
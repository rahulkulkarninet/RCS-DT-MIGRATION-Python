IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = {{EntityID}}
                        AND AccountSpecifics_MetaFieldGroupID = {{AccountSpecificsGroupID}}
              )

        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( {{EntityID}} ,
                  {{AccountSpecificsGroupID}} ,
                  1 ,
                  {{CurrentSessionID}} ,
                  GETDATE() ,
                  1 ,
                  1
                )
;
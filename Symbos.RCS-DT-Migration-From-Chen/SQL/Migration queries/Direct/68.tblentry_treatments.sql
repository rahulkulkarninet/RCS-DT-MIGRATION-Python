
IF {{EntryTypeID_Treatment}} = -1
    BEGIN
        RAISERROR('EntryTypeID_Treatment did not resolve - no tblEntryType row matches the configured EntryType name. Treatments would be written as System Notes. Fix the filter_value in migration_variables.json for this environment.', 16, 1);
        RETURN;
    END
;


INSERT  INTO tblEntry WITH ( TABLOCK )
        ( EntryTypeID ,
          EntryStatusID ,
          AccountID ,
          [Entry] ,
          EntryDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  {{EntryTypeID_Treatment}} ,
                1 ,
                A.AccountID ,
                T.[Entry] ,
                T.LastTreatmentDate ,
                1 ,
                {{CurrentSessionID}} ,
                T.LastTreatmentDate ,
                1 ,
                {{LoadID}}
        FROM    tblAccount A WITH ( NOLOCK )
                CROSS APPLY ( VALUES ( TRY_CONVERT(INT, A.AccountNumberPrevious) ) )
                    AS K ( MatchKey )
                CROSS APPLY ( SELECT STRING_AGG(CAST(N'--- '
                                            + CONVERT(VARCHAR(10), R.Treatment_Date, 103)
                                            + N' ' + CONVERT(VARCHAR(5), R.Treatment_Date, 108)
                                            + N' ---' + CHAR(13) + CHAR(10)
                                            + CONCAT(R.Treatment_Step, ' - ',
                                                     R.Treatment_Type, ' - ',
                                                     R.Treatment_Result_Code, ' - ',
                                                     R.Treatment_Result, ' - ',
                                                     R.Treatment_Code, ' - ',
                                                     R.Treatment_Description)
                                            AS NVARCHAR(MAX)) ,
                                        CHAR(13) + CHAR(10) + CHAR(13) + CHAR(10))
                                        WITHIN GROUP ( ORDER BY R.Treatment_Date DESC ) ,
                                     MAX(R.Treatment_Date)
                              FROM   RC_TREATMENT R WITH ( NOLOCK )
                              WHERE  R.Full_Debt_Code = K.MatchKey
                            ) AS T ( [Entry] , LastTreatmentDate )
        WHERE   A.LoadID = {{LoadID}}
                AND K.MatchKey IS NOT NULL
                AND T.[Entry] IS NOT NULL
        OPTION  ( RECOMPILE );

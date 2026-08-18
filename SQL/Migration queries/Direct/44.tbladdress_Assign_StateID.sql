UPDATE  ADR
SET     StateID = S.StateID
FROM    tblAddress ADR WITH ( ROWLOCK )
        LEFT JOIN tblState S WITH ( ROWLOCK ) ON ADR.State = S.StateShort
WHERE   ADR.LoadID = {{LoadID}}
        AND ADR.StateID IS NULL
;
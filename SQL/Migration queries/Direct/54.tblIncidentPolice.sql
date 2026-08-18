INSERT INTO tblIncidentPolice WITH (ROWLOCK)
    (
        AccountIncidentID,
        PoliceAttended,
        FileNumber,
        PoliceStation,
        CreateID,
        CreateSessionID,
        CreateTS,
        StatusID,
        LoadID
    )
SELECT
    AI.AccountIncidentID,
    0, 
    DR.Police_Report,
    DR.Police_Station,
    1,
    {{CurrentSessionID}},
    GETDATE(),
    1,
    {{LoadID}}
FROM tblaccount A
    JOIN tblAccountIncident AI ON AI.AccountID = A.AccountID
    JOIN RC_DEBTOR DR ON DR.Debt_Code = A.AccountNumberPrevious
WHERE A.loadID = {{LoadID}}
  AND LEN(DR.Police_Report) > 0
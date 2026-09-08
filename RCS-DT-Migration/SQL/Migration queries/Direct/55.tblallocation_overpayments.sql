
INSERT INTO tblallocation
        (AccountID ,
		PaymentID,
		PrincipalID,
		CostID,
		AllocationTypeID,
		Allocation,
        CreateID ,
        CreateSessionID ,
        CreateTS ,
        StatusID
        )
SELECT
		a.AccountID,
		p.PaymentID,
		NULL,
		NULL,
		4, -- alloc type 'overpayment'
		p.LUPAllocatedOverpayment,
		1,
		{{CurrentSessionID}},
		GETDATE(),
		1

FROM tblpayment p
INNER join tblaccount a on a.accountid = p.AccountID
where a.loadid = {{LoadID}}
AND p.LUPAllocatedOverpayment != 0
;
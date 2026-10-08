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
				pr.PrincipalID,
				NULL,
				1, -- alloc type 'principal'
				p.LUPAllocatedPrincipal,
				1,
				{{CurrentSessionID}},
				GETDATE(),
				1

		FROM tblpayment p
		INNER join tblaccount a on a.accountid = p.AccountID
		INNER JOIN tblprincipal pr on a.accountid = pr.AccountID
		where a.loadid = {{LoadID}}
		AND p.LUPAllocatedPrincipal != 0
		AND CAST(pr.Z_REF AS NVARCHAR) = CAST(p.Z_REF AS NVARCHAR)
;
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
		c.CostID,
		2, -- alloc type 'cost'
		p.LUPAllocatedCost,
		1,
		{{CurrentSessionID}},
		GETDATE(),
		1

from tblpayment p
INNER join tblaccount a on a.accountid = p.AccountID
INNER JOIN tblCost c on a.accountid = c.AccountID
where a.loadid = {{LoadID}}
and p.LUPAllocatedCost != 0
;
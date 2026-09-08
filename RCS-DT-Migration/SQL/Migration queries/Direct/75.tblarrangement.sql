INSERT  INTO tblArrangement WITH ( ROWLOCK )
        ( AccountID ,
          ArrangementAmount ,
          CreateID ,
          CreateSessionID ,
          ArrangementTypeID ,--ArrangmentType, to run via mapping table
          NumberOfInstallmentPayments ,
          CommenceDate ,
          ArrangementEndDate ,
          BankTransactionMethodID ,--BankTransactionMethodID, to run via mapping table
          LUPTotalPayments ,
          LUPArrangementBalance ,
          AccountBalanceAtArrangement ,
          CreateTS ,
          StatusID ,
          ArrangementStatusID ,
          FrequencyID ,
          LoadID,
          ArrangementDate
        )
        SELECT  A.AccountID ,		
                DL.Deal_Amount ,
                1 ,
                {{CurrentSessionID}} ,
                ISNULL({{ArrangementTypeID_Deal}}, 1) ,
                DL.No_Instalments ,
                DL.First_Instalment ,
                DL.Last_Instal_Date ,
                1 ,--BankTransactionMethodID, to run via mapping table
                DL.Total_Paid ,
                DL.Total_Outstanding ,
                DL.Bal_At_Tme_Of_Offer ,
                DL.Date_of_Deal , --GETDATE(),
                1 ,
                CASE 
                    WHEN (DL.Deal_Amount - ISNULL(DL.Total_Paid,0) <= 0) THEN 2 --Successful
                    WHEN ((DL.Deal_Amount - ISNULL(DL.Total_Paid,0) > 0) AND DATEDIFF(DAY, DL.Due_Date, GETDATE()) < 0) THEN 4 -- Failed
                    ELSE 1 -- In Progress                    
                END ,  
                NULL ,  --Deal is an Ad-hoc arrangement, no frequency4
                {{LoadID}},
                DL.Date_of_Deal
        FROM    [RC_DEAL] DL
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = DL.Extended_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
        ;

INSERT  INTO tblInvoice WITH ( ROWLOCK )
        ( EntityID ,
          AccountID ,
          InvoiceDesc ,
          IssueDate ,
          InvoiceFromDate ,
          InvoiceToDate ,
          PaymentToSelection ,
          InvoiceTotal ,
          CreateTS ,
          CreateID ,
          CreateSessionID ,
          StatusID ,
          InvoiceRef ,
          Reversed
        )
        SELECT  {{EntityID}} ,
                A.AccountID ,
                S.Particulars ,
                S.[Date] ,
                NULL ,
                NULL ,
                '2' , --Direct
                NULL , --RC TO Provide Field
                S.[Date] , --GETDATE(),
                1 ,
                {{CurrentSessionID}} ,
                1 ,
                S.Tran_Key ,
                0
        FROM    RC_STATEMENT S
                LEFT JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = S.Extended_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
        ;
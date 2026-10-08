
-- Credit bureau listings from RC_CCB_CCN_EXTRACT, one tracking row per account.
--
-- The extract names every listing column CCB_*, commercial or consumer alike;
-- Type is what decides. COMMERCIAL rows fill the CCN columns (ccn_*, mg_key,
-- ccn_bureau_key), CONSUMER rows the CCB ones (ccb_*, ccb_key, ccb_mg_key). A
-- row with any other Type is not migrated.
--
-- last_sent_* are filled from what RCS last lodged, so DebtRak's status and
-- balance triggers see no change on the first outbound run after cut-over and
-- do not re-send every migrated listing.
--
-- Only testse and uat have the credit reporting tables; elsewhere this is a no-op.
IF OBJECT_ID(N'dbo.tblCredit_ReportingTracking', N'U') IS NOT NULL
BEGIN

INSERT  INTO tblCredit_ReportingTracking WITH ( ROWLOCK )
        ( account_id ,
          ccn_status ,
          ccn_status_date ,
          ccb_status ,
          ccb_status_date ,
          listing_balance ,
          balance_outstanding ,
          last_update_sent ,
          last_update_received ,
          original_date_sent ,
          delete_date ,
          bureau_error_feedback ,
          bureau_warn_feedback ,
          mg_key ,
          ccn_bureau_key ,
          ccb_key ,
          ccb_mg_key ,
          aplan_status ,
          aplan_date ,
          ccb_product ,
          ccb_flag ,
          ccb_last_updated ,
          listed_name ,
          last_sent_amt_paid ,
          last_sent_aplan_status ,
          last_sent_comp_date ,
          last_sent_orig_debt ,
          last_sent_tot_due ,
          ccn_update_date ,
          bureau_code ,
          create_ts ,
          create_id
        )
        SELECT  A.AccountID ,
                CASE WHEN K.IsCcn = 1 THEN S.ListingStatus END ,
                CASE WHEN K.IsCcn = 1 THEN S.ListingStatusDate END ,
                CASE WHEN K.IsCcn = 0 THEN S.ListingStatus END ,
                CASE WHEN K.IsCcn = 0 THEN S.ListingStatusDate END ,
                CCB.CCB_Listing_Balance ,
                CCB.CCB_Balance_Outstanding ,
                CCB.CCB_Last_Sent_Date ,
                CCB.CCB_Update_Received_Date ,
                CCB.CCB_Orig_Sent_date ,
                CCB.CCB_Closed_Date ,
                -- "code - description", and for a warning "- field: value" after
                -- it. Any part can be blank on its own (a description with no
                -- code, a value with no field), so each is dropped when empty.
                NULLIF(CONCAT_WS(' - ', NULLIF(LTRIM(RTRIM(CCB.CCB_Error_Code)), ''),
                                        NULLIF(LTRIM(RTRIM(CCB.CCB_Error_Description)), '')), '') ,
                NULLIF(CONCAT_WS(' - ', NULLIF(LTRIM(RTRIM(CCB.CCB_Warning_Codes)), ''),
                                        NULLIF(LTRIM(RTRIM(CCB.CCB_Warning_Description)), ''),
                                        NULLIF(CONCAT_WS(': ', NULLIF(LTRIM(RTRIM(CCB.CCB_Warning_Field)), ''),
                                                               NULLIF(LTRIM(RTRIM(CCB.CCB_Warning_Value)), '')), '')), '') ,
                CASE WHEN K.IsCcn = 1 THEN CCB.CCB_MG_UniqueKey END ,
                CASE WHEN K.IsCcn = 1 THEN CCB.CCB_Bureau_Unique_Key END ,
                CASE WHEN K.IsCcn = 0 THEN CCB.CCB_Bureau_Unique_Key END ,
                CASE WHEN K.IsCcn = 0 THEN CCB.CCB_MG_UniqueKey END ,
                CCB.APLAN_Status ,
                CCB.APLAN_Status_Date ,
                CASE WHEN K.IsCcn = 0 THEN CCB.CCB_Product END ,
                CASE WHEN K.IsCcn = 0 THEN CCB.CCB_Flag END ,
                CASE WHEN K.IsCcn = 0 THEN CCB.CCB_Last_Sent_Date END ,
                CCB.Debtor_Name ,
                -- Never negative: interest or costs can leave the outstanding
                -- balance above what was listed.
                CASE WHEN CCB.CCB_Balance_Outstanding > CCB.CCB_Listing_Balance THEN 0
                     ELSE CCB.CCB_Listing_Balance - CCB.CCB_Balance_Outstanding END ,
                CCB.APLAN_Status ,
                CCB.CCB_Closed_Date ,
                CCB.CCB_Listing_Balance ,
                CCB.CCB_Balance_Outstanding ,
                CASE WHEN K.IsCcn = 1 THEN CCB.CCB_Last_Sent_Date END ,
                B.BureauCode ,
                GETDATE() ,
                1
        FROM    RC_CCB_CCN_EXTRACT CCB
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CCB.Extended_Debt_Code
                CROSS APPLY ( SELECT ISNULL(NULLIF(UPPER(LTRIM(RTRIM(CCB.Provider))), ''), 'ILLION') AS BureauCode ) B
                CROSS APPLY ( SELECT CASE UPPER(LTRIM(RTRIM(CCB.Type)))
                                         WHEN 'COMMERCIAL' THEN 1
                                         WHEN 'CONSUMER'   THEN 0
                                     END AS IsCcn
                            ) K
                -- A closed listing has been withdrawn from the bureau; anything
                -- else is still listed, as of the date it was first lodged.
                CROSS APPLY ( SELECT CASE WHEN CCB.CCB_Closed_Date IS NOT NULL THEN 'WITHDRAWN' ELSE 'LISTED' END AS ListingStatus ,
                                     ISNULL(CCB.CCB_Closed_Date, CCB.CCB_Orig_Sent_date) AS ListingStatusDate
                            ) S
        WHERE   A.LoadID = {{LoadID}}
                AND K.IsCcn IS NOT NULL
                -- Tracking is keyed per account and bureau (its index is on both),
                -- so an account listed with another bureau is no reason to skip.
                AND NOT EXISTS ( SELECT 1 FROM tblCredit_ReportingTracking X WITH ( NOLOCK )
                                 WHERE  X.account_id = A.AccountID
                                        AND X.bureau_code = B.BureauCode )
;

-- The listed debtor. ZID is the reference RCS lodged the debtor under.
INSERT  INTO tblCredit_ReportingTrackingDefendant WITH ( ROWLOCK )
        ( TrackingID ,
          DefendantOrdinal ,
          DebtorID ,
          ThirdPartySourceReference ,
          CcbKey ,
          CreateTS ,
          CreateID
        )
        SELECT  T.id ,
                1 ,
                AC.ContactID ,
                COALESCE(NULLIF(LTRIM(RTRIM(CCB.ZID)), ''), CCB.Debtor_Code, CAST(CCB.Extended_Debt_Code AS NVARCHAR(50))) ,
                T.ccb_key ,
                GETDATE() ,
                1
        FROM    RC_CCB_CCN_EXTRACT CCB
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CCB.Extended_Debt_Code
                CROSS APPLY ( SELECT ISNULL(NULLIF(UPPER(LTRIM(RTRIM(CCB.Provider))), ''), 'ILLION') AS BureauCode ) B
                INNER JOIN tblCredit_ReportingTracking T WITH ( NOLOCK ) ON T.account_id = A.AccountID
                                                                         AND T.bureau_code = B.BureauCode
                OUTER APPLY ( SELECT TOP 1 X.ContactID
                              FROM   tblAccount_Contact X WITH ( NOLOCK )
                              WHERE  X.AccountID = A.AccountID
                                     AND X.RelationshipID = 1 -- Primary Debtor
                              ORDER BY X.ContactID
                            ) AC
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblCredit_ReportingTrackingDefendant D WITH ( NOLOCK )
                                 WHERE  D.TrackingID = T.id
                                        AND D.DefendantOrdinal = 1 )
;

END

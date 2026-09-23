INSERT  INTO tblDocument WITH ( ROWLOCK )
        ( AccountID ,
          Document ,
          DocumentTemplateID ,
          DocumentTemplateVersionID ,
          MetaValue_DocumentGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_IDSTR
        )
        SELECT  A.AccountID ,
                D.Document_Code ,
                DT.DocumentTemplateID ,
                LatestVersion.DocumentTemplateVersionID ,
                MVG.MetaValue_DocumentGroupID ,
                ISNULL(OM.ContactID, {{DefaultOperatorContactID}}) ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                D.Note_Key
        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON CONVERT(nvarchar(100), D.Extended_Debt_Code) = A.AccountNumberPrevious
                INNER JOIN tblDocumentTemplate DT WITH ( NOLOCK ) ON DT.DocumentTemplateCode = D.Document_Code
                CROSS APPLY ( SELECT TOP 1
                                        DocumentTemplateVersionID ,
                                        MetaField_DocumentGroupID
                              FROM      tblDocumentTemplateVersion WITH ( NOLOCK )
                              WHERE     DocumentTemplateID = DT.DocumentTemplateID
                                        AND StatusID = 1
                              ORDER BY  DocumentTemplateVersionID DESC
                            ) LatestVersion
                INNER JOIN tblMetaValue_DocumentGroup MVG WITH ( NOLOCK ) ON MVG.Z_IDSTR = CONVERT(nvarchar(200), D.Note_Key)
                OUTER APPLY ( SELECT TOP 1
                                        C.ContactID
                              FROM      tblContact C WITH ( NOLOCK )
                              WHERE     C.UserName = LTRIM(RTRIM(REPLACE(D.Operator_Code, NCHAR(160), ' ')))
                              ORDER BY  CASE WHEN ISNULL(C.StatusID, 0) = 1 THEN 0 ELSE 1 END ,
                                        C.ContactID
                            ) OM
        WHERE   A.LoadID = {{LoadID}}
                AND A.StatusID = 1
                AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')
        ;
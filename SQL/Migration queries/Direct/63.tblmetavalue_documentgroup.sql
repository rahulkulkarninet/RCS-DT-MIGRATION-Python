INSERT  INTO tblMetaValue_DocumentGroup
        ( MetaField_DocumentGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_IDSTR
        )
        SELECT  LatestVersion.MetaField_DocumentGroupID ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                D.Note_Key
        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON D.Extended_Debt_Code = A.AccountNumberPrevious
                INNER JOIN tblDocumentTemplate DT WITH ( NOLOCK ) ON DT.DocumentTemplateCode = D.Document_Code
                CROSS APPLY ( SELECT TOP 1
                                        DocumentTemplateVersionID ,
                                        MetaField_DocumentGroupID
                              FROM      tblDocumentTemplateVersion WITH ( NOLOCK )
                              WHERE     DocumentTemplateID = DT.DocumentTemplateID
                                        AND StatusID = 1
                              ORDER BY  DocumentTemplateVersionID DESC
                            ) LatestVersion
        WHERE   A.LoadID = {{LoadID}}
                AND A.StatusID = 1
                AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')
;
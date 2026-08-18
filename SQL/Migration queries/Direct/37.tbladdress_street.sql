WITH AddressParts AS (
    SELECT 
        C.ContactID,
        C.CreateTS,
        ROW_NUMBER() OVER (PARTITION BY C.ContactID ORDER BY (SELECT NULL)) AS RowNum,
        LTRIM(RTRIM(value)) AS value
    FROM tblContact C WITH (NOLOCK)
    INNER JOIN RC_DEBTOR RCC ON RCC.Debtor_Code = C.Z_REF2
    CROSS APPLY STRING_SPLIT(RCC.Street_Address, '|')
    WHERE C.LoadID = {{LoadID}}

),
PivotedAddress AS (
    SELECT 
        ContactID,
        CreateTS,
        MAX(CASE WHEN RowNum = 1 THEN value END) AS address,
        MAX(CASE WHEN RowNum = 2 THEN value END) AS address2,
        MAX(CASE WHEN RowNum = 3 THEN value END) AS address3,
        MAX(CASE WHEN RowNum = 4 THEN value END) AS suburb,
        MAX(CASE WHEN RowNum = 5 THEN value END) AS state,
        MAX(CASE WHEN RowNum = 6 THEN value END) AS postcode
    FROM AddressParts
    GROUP BY ContactID, CreateTS
)

INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT DISTINCT
            ContactID,
            {{AddressTypeID_Home}},
            1,
            CONCAT(
                ISNULL(address, ''),
                CASE WHEN LEN(ISNULL(address2, '')) > 0 THEN CHAR(10) + CHAR(13) + address2 ELSE '' END,
                CASE WHEN LEN(ISNULL(address3, '')) > 0 THEN CHAR(10) + CHAR(13) + address3 ELSE '' END
            ) AS Address,
            state AS State,
            suburb AS Suburb,
            postcode AS Postcode,
            {{DefaultCountryID}},
            1,
            1,
            {{CurrentSessionID}},
            CreateTS,
            {{LoadID}}
        FROM PivotedAddress
        WHERE address IS NOT NULL OR suburb IS NOT NULL; -- Only include records with meaningful address data
        ;
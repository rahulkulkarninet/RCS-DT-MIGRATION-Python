
SElect distinct
EntityID,
LoadID,
Entity_ID,
Client_Code,
[DATABASE]
From RC_Entity_Mapping  A
left join tblAccount B on A.Entity_ID = B.EntityID